from keras import ops
from keras.api_export import keras_export
from keras.callbacks.callback import Callback


@keras_export("keras.callbacks.SwapEMAWeights")
class SwapEMAWeights(Callback):
    """Swaps EMA weights before and after the evaluation.

    `SwapEMAWeights` callback is used in conjunction with the optimizer using
    `use_ema=True`.

    Note that: we use swapping to save memory. The behavior is undefined if you
    modify the EMA weights or model weights in other callbacks.

    Example:

    ```python
    # Remember to set `use_ema=True`
    model.compile(optimizer=SGD(use_ema=True), loss=..., metrics=...)

    # Metrics will be computed with EMA weights
    model.fit(X_train, Y_train, callbacks=[SwapEMAWeights()])

    # If you want to save model checkpoint with EMA weights, you can set
    # `swap_on_epoch=True` and place ModelCheckpoint after SwapEMAWeights.
    model.fit(
        X_train,
        Y_train,
        callbacks=[SwapEMAWeights(swap_on_epoch=True), ModelCheckpoint(...)]
    )
    ```

    Args:
        swap_on_epoch: whether to perform swapping `on_epoch_begin` and
            `on_epoch_end`. This is useful if you want to use EMA weights for
            other callbacks such as `ModelCheckpoint`. Defaults to `False`.

    """

    def __init__(self, swap_on_epoch=False):
        super().__init__()
        self.swap_on_epoch = swap_on_epoch

        self._ema_weights_in_model = False

    def _swap_variables(self):
        if not hasattr(self.model.optimizer, "_model_variables_moving_average"):
            raise ValueError(
                "SwapEMAWeights must be used when "
                "`_model_variables_moving_average` exists in the optimizer. "
                "Please verify if you have set `use_ema=True` in your "
                f"optimizer. Received: use_ema={self.model.optimizer.use_ema}"
            )
        for var, average_var in zip(
            self.model.trainable_variables,
            self.model.optimizer._model_variables_moving_average,
        ):
            temporary_variable = ops.convert_to_numpy(var)
            var.assign(average_var)
            average_var.assign(temporary_variable)

    def _finalize_ema_values(self):
        if not hasattr(self.model.optimizer, "_model_variables_moving_average"):
            raise ValueError(
                "SwapEMAWeights must be used when "
                "`_model_variables_moving_average` exists in the optimizer. "
                "Please verify if you have set `use_ema=True` in the "
                f"optimizer. Received: use_ema={self.model.optimizer.use_ema}"
            )
        for var, average_var in zip(
            self.model.trainable_variables,
            self.model.optimizer._model_variables_moving_average,
        ):
            average_var.assign(var)

    def on_epoch_begin(self, epoch, logs=None):
        if (
            hasattr(self.model.optimizer, "_model_variables_moving_average")
            and self.swap_on_epoch
            and self._ema_weights_in_model
        ):
            self._swap_variables()
            self._ema_weights_in_model = False

    def on_epoch_end(self, epoch, logs=None):
        if self.swap_on_epoch and not self._ema_weights_in_model:
            self._swap_variables()
            self._ema_weights_in_model = True
            # We need to recover EMA weights from the previously swapped weights
            # in the last epoch. This is becuase, at the end of the fitting,
            # `finalize_variable_values` will be called to assign
            # `_model_variables_moving_average` to `trainable_variables`.
            if epoch == self.params["epochs"] - 1:
                self._finalize_ema_values()

    def on_test_begin(self, logs=None):
        if not self._ema_weights_in_model:
            self._swap_variables()
            self._ema_weights_in_model = True

    def on_test_end(self, logs=None):
        if self._ema_weights_in_model:
            self._swap_variables()
            self._ema_weights_in_model = False

    def on_predict_begin(self, logs=None):
        if not self._ema_weights_in_model:
            self._swap_variables()
            self._ema_weights_in_model = True

    def on_predict_end(self, logs=None):
        if not self._ema_weights_in_model:
            self._swap_variables()
            self._ema_weights_in_model = False
