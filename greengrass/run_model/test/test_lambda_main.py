import unittest
import main
import json
from mock import MagicMock

param_path = './resources/ml/od/deploy_model_algo_1'

class TestModelLoader(unittest.TestCase):
    main.initialize(param_path)

    def test_initialize_model(self):
        main.initialize(param_path)
        self.assertIsNotNone(main.model, 'should return an initialized model object')

    def test_lambda_handler_makes_prediction(self):
        main.initialize(param_path)
        main.client.publish = MagicMock()

        event = {}
        event['filepath'] = './resources/img/blue_box_000001.jpg'
        response = main.lambda_handler(event, {})

        # Assert message published correctly
        self.assertEqual(response['prediction'][0][0], 0.0)
        main.client.publish.assert_called_with(topic='blog/infer/output', payload=json.dumps(response))

    def test_lambda_handler_noops_empty_filepath(self):
        event = {}
        response = main.lambda_handler(event, {})
        self.assertIsNone(response, 'Should return none if no filepath found')
