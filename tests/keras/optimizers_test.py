from __future__ import print_function
import pytest
import numpy as np
from numpy.testing import assert_allclose

from keras.utils import test_utils
from keras import optimizers, Input
from keras.models import Sequential, Model
from keras.layers.core import Dense, Activation, Lambda
from keras.utils.np_utils import to_categorical
from keras import backend as K

num_classes = 2


def get_test_data():
    np.random.seed(1337)
    (x_train, y_train), _ = test_utils.get_test_data(num_train=1000,
                                                     num_test=200,
                                                     input_shape=(10,),
                                                     classification=True,
                                                     num_classes=num_classes)
    y_train = to_categorical(y_train)
    return x_train, y_train


def _test_optimizer(optimizer, target=0.75):
    x_train, y_train = get_test_data()

    model = Sequential()
    model.add(Dense(10, input_shape=(x_train.shape[1],)))
    model.add(Activation('relu'))
    model.add(Dense(y_train.shape[1]))
    model.add(Activation('softmax'))
    model.compile(loss='categorical_crossentropy',
                  optimizer=optimizer,
                  metrics=['accuracy'])

    history = model.fit(x_train, y_train, epochs=2, batch_size=16, verbose=0)
    assert history.history['acc'][-1] >= target
    config = optimizers.serialize(optimizer)
    optim = optimizers.deserialize(config)
    new_config = optimizers.serialize(optim)
    new_config['class_name'] = new_config['class_name'].lower()
    assert config == new_config

    # Test constraints.
    model = Sequential()
    dense = Dense(10,
                  input_shape=(x_train.shape[1],),
                  kernel_constraint=lambda x: 0. * x + 1.,
                  bias_constraint=lambda x: 0. * x + 2.,)
    model.add(dense)
    model.add(Activation('relu'))
    model.add(Dense(y_train.shape[1]))
    model.add(Activation('softmax'))
    model.compile(loss='categorical_crossentropy',
                  optimizer=optimizer,
                  metrics=['accuracy'])
    model.train_on_batch(x_train[:10], y_train[:10])
    kernel, bias = dense.get_weights()
    assert_allclose(kernel, 1.)
    assert_allclose(bias, 2.)


@pytest.mark.skipif((K.backend() != 'tensorflow'),
                    reason="Only Tensorflow raises a "
                           "ValueError if the gradient is null.")
def test_no_grad():
    inp = Input([3])
    x = Dense(10)(inp)
    x = Lambda(lambda l: 1.0 * K.reshape(K.cast(K.argmax(l), 'float32'), [-1, 1]),
               output_shape=lambda x: [x[0], 1])(x)
    mod = Model(inp, x)
    mod.compile('sgd', 'mse')
    with pytest.raises(ValueError):
        mod.fit(np.zeros([10, 3]), np.zeros([10, 1], np.float32),
                batch_size=10, epochs=10)


def test_sgd():
    sgd = optimizers.SGD(lr=0.01, momentum=0.9, nesterov=True)
    _test_optimizer(sgd)
    sgd = optimizers.SGD(learning_rate=0.01, momentum=0.9, decay=0.1, nesterov=True)
    _test_optimizer(sgd)


def test_rmsprop():
    _test_optimizer(optimizers.RMSprop())
    _test_optimizer(optimizers.RMSprop(decay=1e-3))
    _test_optimizer(optimizers.RMSprop(learning_rate=0.1, epsilon=0.01, decay=0.1))
    _test_optimizer(optimizers.RMSprop(learning_rate=0.1, momentum=0.1))
    _test_optimizer(optimizers.RMSprop(learning_rate=0.1, momentum=0.1,
                                       centered=True))


def test_adagrad():
    adagrad = optimizers.Adagrad(lr=0.01)
    _test_optimizer(adagrad)
    _test_optimizer(optimizers.Adagrad(lr=0.01, decay=1e-3))
    new_adagrad = optimizers.Adagrad(learning_rate=0.01,
                                     initial_accumulator_value=0.001,
                                     epsilon=0.001, decay=0.001)
    _test_optimizer(new_adagrad)
    # test backward compatibility for adding opt.iterations.
    assert len(adagrad.get_weights()) == len(new_adagrad.get_weights())
    new_adagrad.set_weights(adagrad.get_weights()[1:])
    _test_optimizer(new_adagrad)


def test_adadelta():
    adadelta = optimizers.Adadelta(lr=1.0)
    _test_optimizer(adadelta, target=0.6)
    _test_optimizer(optimizers.Adadelta(lr=1.0, decay=1e-3), target=0.6)
    new_adadelta = optimizers.Adadelta(learning_rate=1.0,
                                       epsilon=0.001, decay=0.001)
    _test_optimizer(new_adadelta, target=0.6)
    # test backward compatibility for adding opt.iterations.
    assert len(adadelta.get_weights()) == len(new_adadelta.get_weights())
    new_adadelta.set_weights(adadelta.get_weights()[1:])
    _test_optimizer(new_adadelta, target=0.6)


def test_adam():
    adam = optimizers.Adam()
    _test_optimizer(adam)
    _test_optimizer(optimizers.Adam(decay=1e-3))
    new_adam = optimizers.Adam(learning_rate=0.1, epsilon=0.01, decay=0.1)
    _test_optimizer(new_adam)
    num_vars = int((len(adam.weights) - 1) / 2)
    ms = adam.weights[1:(num_vars + 1)]
    adam.weights.extend([K.zeros(K.int_shape(p), dtype=K.dtype(p)) for p in ms])
    new_adam.set_weights(adam.get_weights())
    _test_optimizer(new_adam)


def test_adamax():
    _test_optimizer(optimizers.Adamax(lr=0.002))
    _test_optimizer(optimizers.Adamax(lr=0.002, decay=1e-3))
    _test_optimizer(optimizers.Adamax(learning_rate=0.002, epsilon=0.001,
                                      decay=0.001))


def test_nadam():
    nadam = optimizers.Nadam()
    _test_optimizer(nadam)
    new_nadam = optimizers.Nadam(learning_rate=0.1, epsilon=0.01, schedule_decay=0.1)
    _test_optimizer(new_nadam)
    # test backward compatibility for adding opt.m_schedule.
    assert len(nadam.get_weights()) == len(new_nadam.get_weights())
    weights = nadam.get_weights()
    new_nadam.set_weights([weights[0]] + weights[1:])
    _test_optimizer(new_nadam)


def test_adam_amsgrad():
    _test_optimizer(optimizers.Adam(amsgrad=True))
    _test_optimizer(optimizers.Adam(amsgrad=True, decay=1e-3))


def test_clipnorm():
    sgd = optimizers.SGD(lr=0.01, momentum=0.9, clipnorm=0.5)
    _test_optimizer(sgd)


def test_clipvalue():
    sgd = optimizers.SGD(lr=0.01, momentum=0.9, clipvalue=0.5)
    _test_optimizer(sgd)


@pytest.mark.skipif((K.backend() != 'tensorflow'),
                    reason='Requires TensorFlow backend')
def test_tfoptimizer():
    from keras import constraints
    from tensorflow import train
    optimizer = optimizers.TFOptimizer(train.AdamOptimizer())
    model = Sequential()
    model.add(Dense(num_classes, input_shape=(3,),
                    kernel_constraint=constraints.MaxNorm(1)))
    model.compile(loss='mean_squared_error', optimizer=optimizer)
    model.fit(np.random.random((5, 3)), np.random.random((5, num_classes)),
              epochs=1, batch_size=5, verbose=0)
    # not supported
    with pytest.raises(NotImplementedError):
        optimizer.weights
    with pytest.raises(NotImplementedError):
        optimizer.get_config()
    with pytest.raises(NotImplementedError):
        optimizer.from_config(None)


@pytest.mark.skipif((K.backend() != 'tensorflow'),
                    reason='Requires TensorFlow backend')
def test_tfoptimizer_pass_correct_named_params_to_native_tensorflow_optimizer():
    from keras import constraints
    from tensorflow import train

    class MyTfOptimizer(train.Optimizer):
        wrapping_optimizer = train.AdamOptimizer()

        def compute_gradients(self, loss, **kwargs):
            return super(MyTfOptimizer, self).compute_gradients(loss, **kwargs)

        def apply_gradients(self, grads_and_vars, **kwargs):
            return self.wrapping_optimizer.apply_gradients(grads_and_vars,
                                                           **kwargs)
    my_tf_optimizer = MyTfOptimizer(use_locking=False, name='MyTfOptimizer')
    optimizer = optimizers.TFOptimizer(my_tf_optimizer)
    model = Sequential()
    model.add(Dense(num_classes, input_shape=(3,),
                    kernel_constraint=constraints.MaxNorm(1)))
    model.compile(loss='mean_squared_error', optimizer=optimizer)
    model.fit(np.random.random((5, 3)), np.random.random((5, num_classes)),
              epochs=1, batch_size=5, verbose=0)


if __name__ == '__main__':
    pytest.main([__file__])
