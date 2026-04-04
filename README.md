# WBLogistic_SealsTeam

## File Structure

```bash
WBLogistic_SealsTeam/
├── data/                                    # Сырые данные (.gitignore)
│   ├── train_team_track.parquet
│   └── test_team_track.parquet
│
├── models/                                  # Веса моделей (.gitignore)
│   ├── ensemble_chain_catboost.cbm          # Модель 1: Цепной CatBoost
│   ├── ensemble_chain_lightgbm.txt          # Модель 2: Цепной LightGBM
│   ├── macro_daily_prophet.pkl              # Модель 3: Prophet
│   └── best_k_multiplier.json               # Коэффициент для метрики
│
├── config/                                  # Конфигурация Python-части
│   ├── settings.yaml                        # Бизнес-правила (SLA_HOURS=6, TRUCK_CAPACITY=30)
│   ├── logging.yaml                         # Настройки логирования
│   └── .env.example                         # Шаблон портов и хостов
│
├── src/
│   ├── ml_pipeline/                         # Оффлайн: обучение моделей
│   │   ├── features.py
│   │   ├── train_micro.py                   # CLI/скрипт оффлайн-обучения micro-модели
│   │   ├── train_macro.py                   # CLI/скрипт оффлайн-обучения macro-модели
│   │   ├── metrics.py
│   │   └── predict_submission.py            # CLI/скрипт генерации submission / batch prediction
│   │
│   ├── backend_service/                     # Python FastAPI: ML + Decision Engine
│   │   ├── main.py                          # FastAPI entry-point (uvicorn), app bootstrap
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routers.py                   # HTTP слой: /health, /predict, оркестрация
│   │   │   │                                # forecast -> dispatch pipeline
│   │   │   └── schemas.py                   # Pydantic-схемы
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py                    # YAML settings loader + validation
│   │   │   ├── exceptions.py                # Кастомные обработчики ошибок API
│   │   │   └── feature_logger.py            # Background JSONL с request/response + pipeline state
│   │   └── engine/
│   │       ├── forecaster_micro.py          # Инференс micro (10 шагов)
│   │       ├── forecaster_macro.py          # Инференс macro (7 дней)
│   │       └── auto_dispatcher.py           # Прогноз → заявки
│   │
│   └── frontend_ui/                         # Flet UI
│       ├── app.py                           # Инициализация Flet, роутинг страниц
│       ├── api_client.py                    # HTTP → Java :8080 (НЕ Python)
│       ├── pages/                           # Экраны приложения
│       │   ├── micro_dispatch.py            # Таблица: Сгенерированные рейсы
│       │   └── macro_planning.py            # График прогноза потребности в ТС на неделю +
│       │                                    # "кнопка" загрузки JSON-сценариев
│       └── components/                      # Переиспользуемые UI-элементы
│           ├── tables.py                    # Рендер датафреймов во Flet
│           └── charts.py                    # Обертки над графиками
│
├── backend-java/                                   # Java Spring Boot: БД + REST API
│   ├── build.gradle
│   ├── settings.gradle
│   ├── gradle.properties                           # org.gradle.java.home=...
│   ├── gradlew                                     # Gradle Wrapper для Linux/macOS
│   ├── gradlew.bat                                 # Gradle Wrapper для Windows
│   ├── Dockerfile                                  # Docker image для Java Spring Boot backend
│   ├── src/main/
│   │   ├── java/com/wb/logistics/
│   │   │   ├── WbLogisticsApplication.java         # Spring Boot entry-point
│   │   │   ├── config/
│   │   │   │   ├── AppProperties.java
│   │   │   │   ├── CorsConfig.java
│   │   │   │   ├── HttpLoggingConfig.java
│   │   │   │   └── LocalProfile.java               # Мок ML для автономного теста
│   │   │   ├── entity/
│   │   │   │   ├── Dispatch.java
│   │   │   │   ├── DispatchStatus.java
│   │   │   │   └── TacticalPlanEntry.java
│   │   │   ├── repository/
│   │   │   │   ├── DispatchRepository.java
│   │   │   │   └── TacticalPlanRepository.java
│   │   │   ├── dto/
│   │   │   │   ├── IngestRequest.java
│   │   │   │   ├── IntegrationData.java            # Погода/пробки/промо
│   │   │   │   ├── DispatchDto.java
│   │   │   │   ├── StatusUpdateRequest.java
│   │   │   │   ├── TacticalPlanDto.java
│   │   │   │   ├── ScheduleResponse.java
│   │   │   │   └── ml/
│   │   │   │       ├── MlPredictionRequest.java    # Данные + интеграции
│   │   │   │       └── MlPredictionResponse.java
│   │   │   ├── mapper/
│   │   │   │   └── DispatchMapper.java
│   │   │   ├── client/
│   │   │   │   └── MlServiceClient.java
│   │   │   ├── service/
│   │   │   │   ├── IngestService.java
│   │   │   │   ├── IntegrationService.java         # Заглушки внешних API
│   │   │   │   ├── DispatchService.java
│   │   │   │   └── TacticalPlanService.java
│   │   │   ├── controller/
│   │   │   │   ├── IngestController.java           # POST /api/v1/ingest-data
│   │   │   │   ├── ScheduleController.java         # GET  /api/v1/schedule
│   │   │   │   └── DispatchController.java         # GET/PATCH /api/v1/dispatch
│   │   │   └── exception/
│   │   │       ├── ResourceNotFoundException.java
│   │   │       ├── MlServiceException.java
│   │   │       └── GlobalExceptionHandler.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── application-local.yml               # H2 + отключённый Flyway
│   │       └── db/migration/
│   │           ├── V1__create_dispatches.sql
│   │           └── V2__create_tactical_plan.sql
│   └── src/test/
│       └── java/com/wb/logistics/                  # (будущие тесты)
│
├── docker-compose.yml                       # postgres + ml-service + backend + frontend
├── docker-compose.python-smoke.yml          # Smoke-стенд для backend-интеграции
├── Dockerfile.ml                            # Docker image для Python FastAPI ML-сервиса
├── tests/...
├── pyproject.toml
├── Makefile
├── README.md
├── .gitignore
└── .github/workflows/lint.yml
```

## Team Notes

