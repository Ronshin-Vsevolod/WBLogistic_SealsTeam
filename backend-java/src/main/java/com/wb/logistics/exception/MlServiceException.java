package com.wb.logistics.exception;

/**
 * Python ML-сервис недоступен или вернул ошибку.
 */
public class MlServiceException extends RuntimeException {
    public MlServiceException(String message) {
        super(message);
    }

    public MlServiceException(String message, Throwable cause) {
        super(message, cause);
    }
}