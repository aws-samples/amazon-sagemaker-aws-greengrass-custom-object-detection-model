import unittest
from src.model_loader import MLModel

param_path = './resources/ml/od/deploy_model_algo_1'

class TestModelLoader(unittest.TestCase):

    def test_initialize_model(self):
        model = MLModel(param_path)
        self.assertIsNotNone(model, 'should return an initialized model object')

    def test_inference_blue_box(self):
        model = MLModel(param_path)
        filepath = './resources/img/blue_box_1_000133.jpg'
        results = model.predict_from_file(filepath)
        self.assert_on_inference(results, 0.0, .70)

    def test_inference_yellow_box(self):
        model = MLModel(param_path)
        filepath = './resources/img/yellow_box_1_000086.jpg'
        results = model.predict_from_file(filepath)
        self.assert_on_inference(results, 1.0, .70)

    def assert_on_inference(self, results, sku, pred_threshold):
        self.assertEqual(results[0][0], sku, 'model made an incorrect prediction')
        self.assertTrue(results[0][1] > pred_threshold, 'model accuracy is below acceptable threshold')
        self.assertEqual(len(results), 1, 'Should only return one boundng box')
        self.assertEqual(len(results[0]), 6, 'did not return correct number of outputs')


if __name__ == '__main__':
    unittest.main()