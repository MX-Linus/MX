from __future__ import print_function
import inspect
import numpy as np
import theano
import copy

from ..layers.advanced_activations import LeakyReLU, PReLU
from ..layers.core import Dense, Merge, Dropout, Activation, Reshape, Flatten, RepeatVector, Layer, AutoEncoder, Masking
from ..layers.core import ActivityRegularization, TimeDistributedDense, AutoEncoder, MaxoutDense
from ..layers.convolutional import Convolution1D, Convolution2D, MaxPooling1D, MaxPooling2D, ZeroPadding2D
from ..layers.embeddings import Embedding, WordContextProduct
from ..layers.noise import GaussianNoise, GaussianDropout
from ..layers.normalization import BatchNormalization
from ..layers.recurrent import SimpleRNN, SimpleDeepRNN, GRU, LSTM, JZS1, JZS2, JZS3
from ..layers import containers
from .. import regularizers
from .. import constraints


def container_from_config(original_layer_dict):
    layer_dict = copy.deepcopy(original_layer_dict)
    name = layer_dict.get('name')

    if name == 'Merge':
        mode = layer_dict.get('mode')
        layers = layer_dict.get('layers')
        layer_list = []
        for layer in layers:
            init_layer = container_from_config(layer)
            layer_list.append(init_layer)
        merge_layer = Merge(layer_list, mode)
        return merge_layer

    elif name == 'Sequential':
        layers = layer_dict.get('layers')
        layer_list = []
        for layer in layers:
            init_layer = container_from_config(layer)
            layer_list.append(init_layer)
        seq_layer = containers.Sequential(layer_list)
        return seq_layer

    elif name == 'Graph':
        graph_layer = containers.Graph()
        inputs = layer_dict.get('input_config')

        for input in inputs:
            graph_layer.add_input(**input)

        nodes = layer_dict.get('node_config')
        for node in nodes:
            layer = container_from_config(layer_dict['nodes'].get(node['name']))
            node['layer'] = layer
            graph_layer.add_node(**node)

        outputs = layer_dict.get('output_config')
        for output in outputs:
            graph_layer.add_output(**output)
        return graph_layer

    elif name == 'AutoEncoder':
        kwargs = {'encoder': container_from_config(layer_dict.get('encoder_config')),
                  'decoder': container_from_config(layer_dict.get('decoder_config'))}
        for kwarg in ['output_reconstruction', 'weights']:
            if kwarg in layer_dict:
                kwargs[kwarg] = layer_dict[kwarg]
        return AutoEncoder(**kwargs)

    else:
        layer_dict.pop('name')

        for k, v in layer_dict.items():
            # For now, this can only happen for regularizers and constraints
            if isinstance(v, dict):
                vname = v.get('name')
                v.pop('name')
                if vname in [x for x, y in inspect.getmembers(constraints, predicate=inspect.isclass)]:
                    layer_dict[k] = constraints.get(vname, v)
                if vname in [x for x, y in inspect.getmembers(regularizers, predicate=inspect.isclass)]:
                    layer_dict[k] = regularizers.get(vname, v)

        base_layer = get_layer(name, layer_dict)
        return base_layer


def print_layer_shapes(model, input_shapes):
    """
    Utility function to print the shape of the output at each layer of a Model

    Arguments:
        model: instance of Model / Merge
        input_shapes: dict (Graph), list of tuples (Merge) or tuple (Sequential)
    """
    if model.__class__.__name__ in ['Sequential', 'Merge']:
        # in this case input_shapes is a tuple, or a list [shape1, shape2]
        if not isinstance(input_shapes[0], tuple):
            input_shapes = [input_shapes]

        inputs = model.get_input(train=False)
        if not isinstance(inputs, list):
            inputs = [inputs]
        input_dummy = [np.zeros(shape, dtype=np.float32)
                       for shape in input_shapes]
        layers = model.layers

    elif model.__class__.__name__ == 'Graph':
        # in this case input_shapes is a dictionary
        inputs = [model.inputs[name].input
                  for name in model.input_order]
        input_dummy = [np.zeros(input_shapes[name], dtype=np.float32)
                       for name in model.input_order]
        layers = [model.nodes[c['name']] for c in model.node_config]

    print("input shapes : ", input_shapes)
    for l in layers:
        shape_f = theano.function(inputs, l.get_output(train=False).shape,
                                  on_unused_input='ignore')
        out_shape = tuple(shape_f(*input_dummy))
        config = l.get_config()
        print('shape after %s: %s' % (config['name'], out_shape))

def get_model_output_size(config, initialX, initialY):
    """Iterate through the layers of a sequential network to determine what the
    total number of output dimensions will be for generation of the iniial 
    dense layer
    
    Parameters
    ----------        
    config : model configuration 
        returned from model.get_config()
        
    initialX : integer 
        shape of the X dimension of the input data
        
    initialY : integer
        shape of the Y dimension of the input data
        
    Usage
    -----
    >>> #initial model construction....
    >>> model.add(Dense(calcDim(model.get_config(), shapeX, shapeY), NUM_HIDDEN_UNITS))
    """
    currX = initialX
    currY = initialY
    
    finalFilter = 1    
    
    for layer in config['layers']:
        
        #check the columns and change x based on border mode
        if layer.get('nb_col'):
            if layer.get('border_mode') == 'valid':
                currX = currX - layer.get('nb_col') + 1
                
        #check the rows and change y based on the border mode
        if layer.get('nb_row'):
            if layer.get('border_mode') == 'valid':
                currY = currY - layer.get('nb_row') + 1
                
        #Even though it's not yet in the documentation the maxpool layer
        #supports stride. If stride is not present the stride faults to the
        #poolsize. If stride is present use it, otherwise use the poolsize
        if layer.get('stride'):
            strideY, strideX = layer.get('stride')
            poolY, poolX = layer.get('poolsize')
            currX = (currX - poolX) / strideX + 1
            currY = (currY - poolY) / strideY + 1
        elif layer.get('poolsize'):
            poolY, poolX = layer.get('poolsize')
            currX = (currX - poolX) / poolX + 1
            currY = (currY - poolY) / poolY + 1
            
        #apply subsample correction
        if layer.get('subsample'):
            subY, subX = layer.get('subsample')
            currX = (currX - subX) / subX + 1
            currY = (currY - subY) / subY + 1
        
        #keep track of the final filter count encountered
        if layer.get('nb_filter'):
            finalFilter = layer.get('nb_filter')
    
    print('finalFilter: %d finalX: %d finaly: %d total: %d' % (finalFilter, 
                                                               currX,  
                                                               currY, 
                                                               finalFilter * currX * currY))
                                                                 
    return finalFilter * currX * currY

from .generic_utils import get_from_module
def get_layer(identifier, kwargs=None):
    return get_from_module(identifier, globals(), 'layer', instantiate=True, kwargs=kwargs)
