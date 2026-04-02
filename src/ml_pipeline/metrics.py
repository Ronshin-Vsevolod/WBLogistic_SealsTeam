import numpy as np


class WapePlusRbias:
    """Calculates as WAPE + Relative Bias."""

    def calculate(self, y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """Рассчитывает значение метрики."""

        wape = (np.abs(y_pred - y_true)).sum() / y_true.sum()

        rbias = np.abs(y_pred.sum() / y_true.sum() - 1)

        return wape + rbias
