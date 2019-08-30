#
# Copyright 2010-2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#

# Lambda entry point
import greengrasssdk
from model_loader import MLModel
import logging
import os
import time
import json

ML_MODEL_BASE_PATH = '/ml/od/'
ML_MODEL_PREFIX = 'deploy_model_algo_1'
ML_MODEL_PATH = os.path.join(ML_MODEL_BASE_PATH, ML_MODEL_PREFIX)
# Creating a greengrass core sdk client
client = greengrasssdk.client('iot-data')
model = None

OUTPUT_TOPIC = 'blog/infer/output'

# Load the model at startup
def initialize(param_path=ML_MODEL_PATH):
    global model
    model = MLModel(param_path)


def lambda_handler(event, context):
    """
    Gets called each time the function gets invoked.
    """
    if 'filepath' not in event:
        msg = 'filepath is not in input event. nothing to do. returning.'
        logging.info(msg)
        client.publish(topic=OUTPUT_TOPIC, payload=msg)
        return None

    filepath = event['filepath']

    if not os.path.exists(filepath): 
        msg = 'filepath does not exist. make sure \'{}\' exists on the device'.format(filepath)
        logging.info(msg)
        client.publish(topic=OUTPUT_TOPIC, payload=msg)
        return None

    logging.info('predicting on image at filepath: {}'.format(filepath))
    start = int(round(time.time() * 1000))
    prediction = model.predict_from_file(filepath)
    end = int(round(time.time() * 1000))

    logging.info('Prediction: {} for file: {} in: {}'.format(prediction, filepath, end - start))

    response = {
        'prediction': prediction,
        'timestamp': time.time(),
        'filepath': filepath
    }
    client.publish(topic=OUTPUT_TOPIC, payload=json.dumps(response))
    return response


# If this path exists then this code is running on the greengrass core and has the ML resources it needs to initialize.
if os.path.exists(ML_MODEL_BASE_PATH):
    initialize()
else:
    logging.info('{} does not exist and we cannot initialize this lambda function.'.format(ML_MODEL_BASE_PATH))
