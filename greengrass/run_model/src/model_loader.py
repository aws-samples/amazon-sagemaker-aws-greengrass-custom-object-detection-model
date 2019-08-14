import mxnet as mx
import numpy as np
import cv2
import logging
from collections import namedtuple
Batch = namedtuple('Batch', ['data'])

DEFAULT_INPUT_SHAPE = 512

def get_ctx():
    """
    Automatically choose the device (CPU or GPU) for running inference
    :return: A list of GPUs available. If no GPU is available, return a list with just the CPU device.
    """
    try:
        gpus = mx.test_utils.list_gpus()
        if len(gpus) > 0:
            ctx = [mx.gpu(gpu) for gpu in gpus]
        else:
            ctx = [mx.cpu()]
    except:
        ctx = [mx.cpu()]
    return ctx


class MLModel(object):
    """
    Loads the pre-trained model which can be found in /ml/od when running on greengrass core or
    from a different path for testing locally.
    """
    def __init__(self, param_path, label_names=[], input_shapes=[('data', (1, 3, DEFAULT_INPUT_SHAPE, DEFAULT_INPUT_SHAPE))]):

        context = get_ctx()[0]
        # Load the network parameters from default epoch 0
        logging.info('Load network parameters from default epoch 0 with prefix: {}'.format(param_path))
        sym, arg_params, aux_params = mx.model.load_checkpoint(param_path, 0)

        # Load the network into an MXNet module and bind the corresponding parameters
        logging.info('Loading network into mxnet module and binding corresponding parameters: {}'.format(arg_params))
        self.mod = mx.mod.Module(symbol=sym, label_names=label_names, context=context)
        self.mod.bind(for_training=False, data_shapes=input_shapes)
        self.mod.set_params(arg_params, aux_params)

    """
    Takes in an image, reshapes it, and runs it through the loaded MXNet graph for inference returning the top label from the softmax
    """
    def predict_from_file(self, filepath, reshape=(DEFAULT_INPUT_SHAPE, DEFAULT_INPUT_SHAPE)):
        # Switch RGB to BGR format (which ImageNet networks take)
        img = cv2.cvtColor(cv2.imread(filepath), cv2.COLOR_BGR2RGB)
        if img is None:
            return []

        # Resize image to fit network input
        img = cv2.resize(img, reshape)
        img = np.swapaxes(img, 0, 2)
        img = np.swapaxes(img, 1, 2)
        img = img[np.newaxis, :]

        self.mod.forward(Batch([mx.nd.array(img)]))
        prob = self.mod.get_outputs()[0].asnumpy()
        prob = np.squeeze(prob)

        # Grab top result, convert to python list of lists and return
        results = [prob[0].tolist()]
        return results


