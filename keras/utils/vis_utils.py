"""Utilities related to model visualization."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os

# `pydot` is an optional dependency,
# see `extras_require` in `setup.py`.
try:
    import pydot
except ImportError:
    pydot = None


def _check_pydot():
    """Raise errors if `pydot` or GraphViz unavailable."""
    if pydot is None:
        raise ImportError(
            'Failed to import `pydot`. '
            'Please install `pydot`. '
            'For example with `pip install pydot`.')
    try:
        # Attempt to create an image of a blank graph
        # to check the pydot/graphviz installation.
        pydot.Dot.create(pydot.Dot())
    except OSError:
        raise OSError(
            '`pydot` failed to call GraphViz.'
            'Please install GraphViz (https://www.graphviz.org/) '
            'and ensure that its executables are in the $PATH.')


def model_to_dot(model,
                 show_shapes=False,
                 show_layer_names=True,
                 rankdir='TB',
                 expand_nested=False,
                 dpi=96,
                 subgraph=False):
    """Convert a Keras model to dot format.

    # Arguments
        model: A Keras model instance.
        show_shapes: whether to display shape information.
        show_layer_names: whether to display layer names.
        rankdir: `rankdir` argument passed to PyDot,
            a string specifying the format of the plot:
            'TB' creates a vertical plot;
            'LR' creates a horizontal plot.
        expand_nested: whether to expand nested models into clusters.
        dpi: dot DPI.
        subgraph: whether to return a pydot.Cluster instance.

    # Returns
        A `pydot.Dot` instance representing the Keras model or
        a `pydot.Cluster` instance representing nested model if
        `subgraph=True`.
    """
    from ..layers.wrappers import Wrapper
    from ..models import Model
    from ..models import Sequential

    _check_pydot()
    if subgraph:
        dot = pydot.Cluster(style = 'dashed', graph_name = model.name)
        dot.set('label', model.name)
        dot.set('labeljust', 'l')
    else:
        dot = pydot.Dot()
        dot.set('rankdir', rankdir)
        dot.set('concentrate', True)
        dot.set('dpi', dpi)
        dot.set_node_defaults(shape='record')

    if isinstance(model, Sequential):
        if not model.built:
            model.build()
    layers = model._layers

    # Create graph nodes.
    for i, layer in enumerate(layers):
        layer_id = str(id(layer))

        # Append a wrapped layer's label to node's label, if it exists.
        layer_name = layer.name
        class_name = layer.__class__.__name__

        if isinstance(layer, Wrapper):
            if expand_nested and isinstance(layer.layer, Model):
                submodel_wrapper = model_to_dot(layer.layer, show_shapes,
                                    show_layer_names, rankdir, expand_nested,
                                    subgraph=True)
                # sub_w : submodel_wrapper
                sub_w_nodes = submodel_wrapper.get_nodes()
                sub_w_first_node = sub_w_nodes[0]
                sub_w_last_node = sub_w_nodes[len(sub_w_nodes) - 1]
                dot.add_subgraph(submodel_wrapper)
            else:
                layer_name = '{}({})'.format(layer_name, layer.layer.name)
                child_class_name = layer.layer.__class__.__name__
                class_name = '{}({})'.format(class_name, child_class_name)

        if expand_nested and isinstance(layer, Model):
            submodel_not_wrapper = model_to_dot(layer, show_shapes,
                                    show_layer_names, rankdir, expand_nested,
                                    subgraph=True)
            # sub_n : submodel_not_wrapper
            sub_n_nodes = submodel_not_wrapper.get_nodes()
            sub_n_first_node = sub_n_nodes[0]
            sub_n_last_node = sub_n_nodes[len(sub_n_nodes) - 1]
            dot.add_subgraph(submodel_not_wrapper)

        # Create node's label.
        if show_layer_names:
            label = '{}: {}'.format(layer_name, class_name)
        else:
            label = class_name

        # Rebuild the label as a table including input/output shapes.
        if show_shapes:
            try:
                outputlabels = str(layer.output_shape)
            except AttributeError:
                outputlabels = 'multiple'
            if hasattr(layer, 'input_shape'):
                inputlabels = str(layer.input_shape)
            elif hasattr(layer, 'input_shapes'):
                inputlabels = ', '.join(
                    [str(ishape) for ishape in layer.input_shapes])
            else:
                inputlabels = 'multiple'
            label = '%s\n|{input:|output:}|{{%s}|{%s}}' % (label,
                                                           inputlabels,
                                                           outputlabels)

        if not expand_nested or not isinstance(layer, Model):
            node = pydot.Node(layer_id, label=label)
            dot.add_node(node)

    # Connect nodes with edges.
    for layer in layers:
        layer_id = str(id(layer))
        for i, node in enumerate(layer._inbound_nodes):
            node_key = layer.name + '_ib-' + str(i)
            if node_key in model._network_nodes:
                for inbound_layer in node.inbound_layers:
                    inbound_layer_id = str(id(inbound_layer))
                    # if inbound_layer is not Model or wrapped Model
                    if (not (expand_nested and (
                            isinstance(inbound_layer, Model)))
                            ) and (
                            not (expand_nested and (
                            isinstance(inbound_layer, Wrapper)) and (
                            isinstance(inbound_layer.layer, Model))) ):
                        # if current layer is not Model or wrapped Model
                        if (not (expand_nested and (
                                isinstance(layer, Model)))
                                ) and (
                                not (expand_nested and
                                (isinstance(layer, Wrapper)) and (
                                isinstance(layer.layer, Model))) ):
                            assert dot.get_node(inbound_layer_id)
                            assert dot.get_node(layer_id)
                            dot.add_edge(pydot.Edge(inbound_layer_id, layer_id))
                        # if current layer is Model
                        elif expand_nested and isinstance(layer, Model):
                            if not dot.get_edge(inbound_layer_id,
                                                sub_n_first_node.get_name()):
                                dot.add_edge(pydot.Edge(inbound_layer_id,
                                                sub_n_first_node.get_name()))
                        # if current layer is wrapped Model
                        elif expand_nested and isinstance(layer, Wrapper) and (
                                isinstance(layer.layer, Model)):
                            dot.add_edge(pydot.Edge(inbound_layer_id, layer_id))
                            dot.add_edge(pydot.Edge(layer_id,
                                                sub_w_first_node.get_name()))
                    # if inbound_layer is Model
                    elif expand_nested and isinstance(inbound_layer, Model):
                        if not dot.get_edge(sub_n_last_node.get_name(), layer_id):
                            dot.add_edge(pydot.Edge(sub_n_last_node.get_name(),
                                                        layer_id))
                    # if inbound_layer is wrapped Model
                    elif expand_nested and isinstance(inbound_layer, Wrapper) and (
                                isinstance(inbound_layer.layer, Model)):
                        if not dot.get_edge(sub_w_last_node.get_name(), layer_id):
                            dot.add_edge(pydot.Edge(sub_w_last_node.get_name(),
                                                        layer_id))
    return dot


def plot_model(model,
               to_file='model.png',
               show_shapes=False,
               show_layer_names=True,
               rankdir='TB',
               expand_nested=False,
               dpi=96):
    """Converts a Keras model to dot format and save to a file.

    # Arguments
        model: A Keras model instance
        to_file: File name of the plot image.
        show_shapes: whether to display shape information.
        show_layer_names: whether to display layer names.
        rankdir: `rankdir` argument passed to PyDot,
            a string specifying the format of the plot:
            'TB' creates a vertical plot;
            'LR' creates a horizontal plot.
        expand_nested: whether to expand nested models into clusters.
        dpi: dot DPI.

    # Returns
        A Jupyter notebook Image object if Jupyter is installed.
        This enables in-line display of the model plots in notebooks.
    """
    dot = model_to_dot(model, show_shapes, show_layer_names, rankdir,
                       expand_nested, dpi)
    _, extension = os.path.splitext(to_file)
    if not extension:
        extension = 'png'
    else:
        extension = extension[1:]
    dot.write(to_file, format=extension)
    # Return the image as a Jupyter Image object, to be displayed in-line.
    try:
        from IPython import display
        return display.Image(filename=to_file)
    except ImportError:
        pass
