# WBLogistic_SealsTeam

## File Structure

```bash
WBLogistic_SealsTeam/
├── data/                                    # Сырые данные (.gitignore)
│   ├── train_team_track.parquet
│   └── test_team_track.parquet
│
├── models/                                  # Веса моделей (.gitignore)
│   ├── ensemble_chain_catboost.cbm
│   ├── ensemble_chain_lightgbm.txt
│   ├── macro_daily_prophet.pkl
│   └── best_k_multiplier.json
│
├── config/                                  # Конфигурация Python-части
│   ├── settings.yaml
│   ├── logging.yaml
│   └── .env.example
│
├── src/
│   ├── ml_pipeline/                         # Оффлайн: обучение моделей
│   │   ├── features.py
│   │   ├── train_micro.py
│   │   ├── train_macro.py
│   │   ├── metrics.py
│   │   └── predict_submission.py
│   │
│   ├── backend_service/                     # Python FastAPI: ML + Decision Engine
│   │   ├── main.py                          #   uvicorn, POST /predict
│   │   ├── api/
│   │   │   ├── routers.py                   #   POST /predict (вызывается Java)
│   │   │   └── schemas.py                   #   Pydantic-схемы
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── exceptions.py
│   │   │   └── feature_logger.py
│   │   │
│   │   └── engine/
│   │       ├── forecaster_micro.py          #   Инференс micro (10 шагов)
│   │       ├── forecaster_macro.py          #   Инференс macro (7 дней)
│   │       ├── sla_monitor.py               #   FIFO-буфер + SLA
│   │       └── auto_dispatcher.py           #   Прогноз → заявки
│   │
│   └── frontend_ui/                         # Flet UI
│       ├── app.py
│       ├── api_client.py                    #   HTTP → Java :8080 (НЕ Python)
│       ├── pages/
│       │   ├── micro_dispatch.py
│       │   └── macro_planning.py
│       └── components/
│           ├── tables.py
│           └── charts.py
│
├── backend-java/                            # Java Spring Boot: БД + REST API
│   ├── build.gradle
│   ├── settings.gradle
│   ├── gradle.properties                    #   org.gradle.java.home=...
│   ├── Dockerfile
│   ├── src/main/
│   │   ├── java/com/wb/logistics/
│   │   │   ├── WbLogisticsApplication.java
│   │   │   ├── config/
│   │   │   │   ├── AppProperties.java
│   │   │   │   ├── CorsConfig.java
│   │   │   │   ├── HttpLoggingConfig.java
│   │   │   │   └── LocalProfile.java       #   Мок ML для автономного теста
│   │   │   ├── entity/
│   │   │   │   ├── Dispatch.java
│   │   │   │   ├── DispatchStatus.java
│   │   │   │   └── TacticalPlanEntry.java
│   │   │   ├── repository/
│   │   │   │   ├── DispatchRepository.java
│   │   │   │   └── TacticalPlanRepository.java
│   │   │   ├── dto/
│   │   │   │   ├── IngestRequest.java
│   │   │   │   ├── IntegrationData.java     #   Погода/пробки/промо
│   │   │   │   ├── DispatchDto.java
│   │   │   │   ├── StatusUpdateRequest.java
│   │   │   │   ├── TacticalPlanDto.java
│   │   │   │   ├── ScheduleResponse.java
│   │   │   │   └── ml/
│   │   │   │       ├── MlPredictionRequest.java   # Данные + интеграции
│   │   │   │       └── MlPredictionResponse.java
│   │   │   ├── mapper/
│   │   │   │   └── DispatchMapper.java
│   │   │   ├── client/
│   │   │   │   └── MlServiceClient.java
│   │   │   ├── service/
│   │   │   │   ├── IngestService.java
│   │   │   │   ├── IntegrationService.java  #   Заглушки внешних API
│   │   │   │   ├── DispatchService.java
│   │   │   │   └── TacticalPlanService.java
│   │   │   ├── controller/
│   │   │   │   ├── IngestController.java    #   POST /api/v1/ingest-data
│   │   │   │   ├── ScheduleController.java  #   GET  /api/v1/schedule
│   │   │   │   └── DispatchController.java  #   GET/PATCH /api/v1/dispatch
│   │   │   └── exception/
│   │   │       ├── ResourceNotFoundException.java
│   │   │       ├── MlServiceException.java
│   │   │       └── GlobalExceptionHandler.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── application-local.yml        #   H2 + отключённый Flyway
│   │       └── db/migration/
│   │           ├── V1__create_dispatches.sql
│   │           └── V2__create_tactical_plan.sql
│   └── src/test/
│       └── java/com/wb/logistics/            #   (будущие тесты)
│
├── docker-compose.yml                       # postgres + ml-service + backend + frontend
├── Dockerfile.ml                            # Python ML-сервис
├── pyproject.toml
├── Makefile
├── README.md
├── .gitignore
└── .github/workflows/
    └── lint.yml
```

## Team Notes

### Интеллектуальное прогнозирование (ML)
Мы отказались от базового независимого прогнозирования в пользу RegressorChain (Цепной авторегрессии). Поскольку задача требует предсказания на 10 шагов вперед (5 часов), модель каждого следующего шага учитывает предсказание предыдущего. Чтобы снизить дисперсию, мы используем усредненный ансамбль CatBoost и LightGBM с функцией потерь MAE.
В финале мы применяем кастомный оптимизатор на отложенной выборке, который подбирает скалярный множитель k, чтобы идеально сбалансировать штрафы специфичной метрики соревнования (WAPE + Relative Bias). Это идет в файл CSV для судей.

### Веб-Сервис и Конфигурация (Backend)
Система работает не в вакууме. Мы вынесли все жесткие параметры в config/settings.yaml.
Внутри FastAPI крутится Decision Engine (Бизнес-движок). Он получает матрицу предсказаний на 5 часов вперед и симулирует работу склада. Он не просто ждет, пока накопится достаточно груза. Он работает в тандеме с SLA Monitor: если груза мало, но он лежит слишком долго (например, приближается дедлайн 6 часов, заданный в конфиге), движок принудительно инициирует вызов малотоннажного транспорта.

### Интерфейс (Frontend)
Мы используем Flet (Flutter for Python). Это полноценное Single Page Application.
Он имеет строгую структуру: отдельный модуль api_client для общения с бекендом, state.py для кэширования действий диспетчера и компонентную архитектуру страниц. Пользователь видит интерактивные дашборды, где может одним кликом отправить сгенерированный системой JSON-расписание в (симулированную) ERP-систему WB.

### Макро прогнозирование
Мы параллельно используем Prophet для прогнозирования на неделю. Данный инструмент может использовать любые внешние данные как то погода или политика Wildberies (скидки, реклама, что угодно) и корректироваться под любые неожиданные внешние изменения, что позволяет осуществлять заблаговременные запросы транспортных средств.
