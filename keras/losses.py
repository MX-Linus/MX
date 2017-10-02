from __future__ import absolute_import
import six
from . import backend as K
from .utils.generic_utils import (deserialize_keras_object,
                                  serialize_keras_object)


# noinspection SpellCheckingInspection
def mean_squared_error(y_true, y_pred):
    """Mean squared error (MSE)

    A model which minimizes the mean squared error provides an estimate
    of the mean.
    """
    return K.mean(K.square(y_pred - y_true), axis=-1)


def mean_absolute_error(y_true, y_pred):
    """Mean absolute error (MAE)

    A model which minimizes the mean absolute error provides an estimate
    of the median.
    """
    return K.mean(K.abs(y_pred - y_true), axis=-1)


def mean_absolute_percentage_error(y_true, y_pred):
    """Mean absolute percentage error (MAPE)

    Like the mean absolute error, but weighted by `1 / y_true`.
    """
    diff = K.abs((y_true - y_pred) / K.clip(K.abs(y_true),
                                            K.epsilon(),
                                            None))
    return 100. * K.mean(diff, axis=-1)


def mean_squared_logarithmic_error(y_true, y_pred):
    first_log = K.log(K.clip(y_pred, K.epsilon(), None) + 1.)
    second_log = K.log(K.clip(y_true, K.epsilon(), None) + 1.)
    return K.mean(K.square(first_log - second_log), axis=-1)


def squared_hinge(y_true, y_pred):
    return K.mean(K.square(K.maximum(1. - y_true * y_pred, 0.)), axis=-1)


def hinge(y_true, y_pred):
    return K.mean(K.maximum(1. - y_true * y_pred, 0.), axis=-1)


def categorical_hinge(y_true, y_pred):
    pos = K.sum(y_true * y_pred, axis=-1)
    neg = K.max((1. - y_true) * y_pred, axis=-1)
    return K.maximum(0., neg - pos + 1.)


def logcosh(y_true, y_pred):
    """Logarithm of the hyperbolic cosine of the prediction error

    `log(cosh(x))` is approximately equal to `x**2 / 2` for small `x` and
    to `abs(x)` for large `x`. This means it works mostly like the mean
    squared error, but will not be so strongly affected by the occasional
    wildly incorrect prediction.
    """
    def cosh(x):
        return (K.exp(x) + K.exp(-x)) / 2
    return K.mean(K.log(cosh(y_pred - y_true)), axis=-1)


def categorical_crossentropy(y_true, y_pred):
    return K.categorical_crossentropy(y_true, y_pred)


def sparse_categorical_crossentropy(y_true, y_pred):
    return K.sparse_categorical_crossentropy(y_true, y_pred)


def binary_crossentropy(y_true, y_pred):
    return K.mean(K.binary_crossentropy(y_true, y_pred), axis=-1)


def kullback_leibler_divergence(y_true, y_pred):
    y_true = K.clip(y_true, K.epsilon(), 1)
    y_pred = K.clip(y_pred, K.epsilon(), 1)
    return K.sum(y_true * K.log(y_true / y_pred), axis=-1)


def poisson(y_true, y_pred):
    return K.mean(y_pred - y_true * K.log(y_pred + K.epsilon()), axis=-1)


def cosine_proximity(y_true, y_pred):
    y_true = K.l2_normalize(y_true, axis=-1)
    y_pred = K.l2_normalize(y_pred, axis=-1)
    return -K.sum(y_true * y_pred, axis=-1)


class PinballLoss:
    """Pinball loss function for quantile regression

    Minimizing the pinball loss function gives an estimate of a given
    quantile / percentile of the target distribution."""

    def __init__(self, tau):
        """Create a pinball loss function for a given target quantile

        # Arguments
            tau: Target quantile, expressed as a float strictly between 0 and 1
        """
        assert 0 < tau < 1
        self.tau = tau

    def __call__(self, y_true, y_pred):
        loss_prediction_too_low = self.tau * (y_true - y_pred)
        loss_prediction_too_high = (1 - self.tau) * (y_pred - y_true)
        loss = K.switch(K.greater(y_pred, y_true),
                        loss_prediction_too_high,
                        loss_prediction_too_low)
        return K.mean(loss, axis=-1)

    def get_config(self):
        return {'tau': self.tau}


# Aliases.

mse = MSE = mean_squared_error
mae = MAE = mean_absolute_error
mape = MAPE = mean_absolute_percentage_error
msle = MSLE = mean_squared_logarithmic_error
kld = KLD = kullback_leibler_divergence
cosine = cosine_proximity


def serialize(loss):
    return serialize_keras_object(loss)


def deserialize(name, custom_objects=None):
    return deserialize_keras_object(name,
                                    module_objects=globals(),
                                    custom_objects=custom_objects,
                                    printable_module_name='loss function')


def get(identifier):
    if identifier is None:
        return None
    if isinstance(identifier, six.string_types):
        identifier = str(identifier)
        return deserialize(identifier)
    elif callable(identifier):
        return identifier
    else:
        raise ValueError('Could not interpret '
                         'loss function identifier:', identifier)
