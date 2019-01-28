"""Built-in metrics.
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import six
from . import backend as K
from .engine.base_layer import Layer
from .losses import mean_squared_error
from .losses import mean_absolute_error
from .losses import mean_absolute_percentage_error
from .losses import mean_squared_logarithmic_error
from .losses import hinge
from .losses import logcosh
from .losses import squared_hinge
from .losses import categorical_crossentropy
from .losses import sparse_categorical_crossentropy
from .losses import binary_crossentropy
from .losses import kullback_leibler_divergence
from .losses import poisson
from .losses import cosine_proximity
from .utils.generic_utils import deserialize_keras_object
from .utils.generic_utils import serialize_keras_object


def binary_accuracy(y_true, y_pred):
    return K.mean(K.equal(y_true, K.round(y_pred)), axis=-1)


def categorical_accuracy(y_true, y_pred):
    return K.cast(K.equal(K.argmax(y_true, axis=-1),
                          K.argmax(y_pred, axis=-1)),
                  K.floatx())


def sparse_categorical_accuracy(y_true, y_pred):
    # reshape in case it's in shape (num_samples, 1) instead of (num_samples,)
    if K.ndim(y_true) == K.ndim(y_pred):
        y_true = K.squeeze(y_true, -1)
    # convert dense predictions to labels
    y_pred_labels = K.argmax(y_pred, axis=-1)
    y_pred_labels = K.cast(y_pred_labels, K.floatx())
    return K.cast(K.equal(y_true, y_pred_labels), K.floatx())


def top_k_categorical_accuracy(y_true, y_pred, k=5):
    return K.mean(K.in_top_k(y_pred, K.argmax(y_true, axis=-1), k), axis=-1)


def sparse_top_k_categorical_accuracy(y_true, y_pred, k=5):
    # If the shape of y_true is (num_samples, 1), flatten to (num_samples,)
    return K.mean(K.in_top_k(y_pred, K.cast(K.flatten(y_true), 'int32'), k),
                  axis=-1)


class Precision(Layer):
    """Precision metric.
    Stateful representation of Precision.
    a metric for multi-label classification of
    how many selected items are relevant.
    """

    def __init__(self, name='precision', **kwargs):
        super(Precision, self).__init__(name=name, **kwargs)
        self.stateful = True
        self.true_positives = K.variable(value=0, dtype='float32', name='true_positives')
        self.predicted_positives = K.variable(value=0, dtype='float32', name='predicted_positives')

    def reset_states(self):
        K.set_value(self.true_positives, 0)
        K.set_value(self.predicted_positives, 0)

    def __call__(self, y_true, y_pred):
        y_true = K.cast(y_true, 'float32')
        y_pred = K.cast(K.round(y_pred), 'float32')
        correct_preds = K.cast(K.equal(y_pred, y_true), 'float32')
        true_pos = K.cast(K.sum(correct_preds * y_true), 'float32')
        predicted_pos = K.cast(K.sum(K.round(K.clip(y_pred, 0, 1))), 'float32')
        updates = [K.update_add(self.true_positives, true_pos), K.update_add(self.predicted_positives, predicted_pos)]
        self.add_update(updates, inputs=[y_true, y_pred])
        return (self.true_positives * 1) / ((K.epsilon() + self.predicted_positives) * 1)


class Recall(Layer):
    """Recall metric.
    Stateful representation of Recall.
    Computes the recall, a metric for multi-label classification of
    how many relevant items are selected.
    """

    def __init__(self, name='recall', **kwargs):
        super(Recall, self).__init__(name=name, **kwargs)
        self.stateful = True
        self.true_positives = K.variable(value=0, dtype='float32', name='true_positives')
        self.actual_positives = K.variable(value=0, dtype='float32', name='actual_positives')

    def reset_states(self):
        K.set_value(self.true_positives, 0)
        K.set_value(self.actual_positives, 0)

    def __call__(self, y_true, y_pred):
        y_true = K.cast(y_true, 'float32')
        y_pred = K.cast(K.round(y_pred), 'float32')
        correct_preds = K.cast(K.equal(y_pred, y_true), 'float32')
        true_pos = K.cast(K.sum(correct_preds * y_true), 'float32')
        actual_pos = K.cast(K.sum(K.round(K.clip(y_true, 0, 1))), 'float32')
        updates = [K.update_add(self.true_positives, true_pos), K.update_add(self.actual_positives, actual_pos)]
        self.add_update(updates, inputs=[y_true, y_pred])
        return (self.true_positives * 1) / ((self.actual_positives + K.epsilon()) * 1)


class FBetaScore(Layer):
    """Computes the F score.
    The F score is the weighted harmonic mean of precision and recall.
    This is useful for multi-label classification, where input samples can be
    classified as sets of labels. By only using accuracy (precision) a model
    would achieve a perfect score by simply assigning every class to every
    input. In order to avoid this, a metric should penalize incorrect class
    assignments as well (recall). The F-beta score (ranged from 0.0 to 1.0)
    computes this, as a weighted mean of the proportion of correct class
    assignments vs. the proportion of incorrect class assignments.
    With beta = 1, this is equivalent to a F-measure. With beta < 1, assigning
    correct classes becomes more important, and with beta > 1 the metric is
    instead weighted towards penalizing incorrect class assignments.
    """

    def __init__(self, name='fbeta_score', beta=1, **kwargs):
        if beta < 0:
            raise ValueError('The lowest choosable beta is zero (only precision).')
        super(FBetaScore, self).__init__(name=name, **kwargs)
        self.beta = beta
        self.stateful = True
        self.true_positives = K.variable(value=0, dtype='float32', name='true_positives')
        self.false_positives = K.variable(value=0, dtype='float32', name='false_positives')
        self.false_negatives = K.variable(value=0, dtype='float32', name='false_negatives')

    def reset_states(self):
        K.set_value(self.true_positives, 0)
        K.set_value(self.false_positives, 0)
        K.set_value(self.false_negatives, 0)

    def __call__(self, y_true, y_pred):
        y_true = K.cast(y_true, 'float32')
        y_pred = K.cast(K.round(y_pred), 'float32')

        y_pred_pos = K.round(K.clip(y_pred, 0, 1))
        y_pred_neg = 1 - y_pred_pos

        y_pos = K.round(K.clip(y_true, 0, 1))
        y_neg = 1 - y_pos

        tp = K.cast(K.sum(y_pos * y_pred_pos), 'float32')
        fp = K.cast(K.sum(y_neg * y_pred_pos), 'float32')
        fn = K.cast(K.sum(y_pos * y_pred_neg), 'float32')

        updates = [K.update_add(self.true_positives, tp),
                   K.update_add(self.false_positives, fp),
                   K.update_add(self.false_negatives, fn)]
        self.add_update(updates, inputs=[y_true, y_pred])

        return ((1 + self.beta ** 2) * self.true_positives) / (((1 + self.beta ** 2) * self.true_positives + K.epsilon()) + (self.beta ** 2) * self.false_negatives + self.false_positives)


# Aliases

mse = MSE = mean_squared_error
mae = MAE = mean_absolute_error
mape = MAPE = mean_absolute_percentage_error
msle = MSLE = mean_squared_logarithmic_error
cosine = cosine_proximity
precision = Precision()
recall = Recall()
f1 = fscore = f1score = fmeasure = FBetaScore(name='f1_score', beta=1)


def serialize(metric):
    return serialize_keras_object(metric)


def deserialize(config, custom_objects=None):
    return deserialize_keras_object(config,
                                    module_objects=globals(),
                                    custom_objects=custom_objects,
                                    printable_module_name='metric function')


def get(identifier):
    if isinstance(identifier, dict):
        config = {'class_name': str(identifier), 'config': {}}
        return deserialize(config)
    elif isinstance(identifier, six.string_types):
        return deserialize(str(identifier))
    elif callable(identifier):
        return identifier
    else:
        raise ValueError('Could not interpret '
                         'metric function identifier:', identifier)
