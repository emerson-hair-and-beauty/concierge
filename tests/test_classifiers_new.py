import unittest
from app.agents.input.lib.classifier import (
    classify_moisture_behaviour,
    classify_texture,
    classify_humidity_response
)
from app.agents.input.lib.find_advice import collateAdvice

class TestClassifiers(unittest.TestCase):

    def test_moisture_behaviour_new_labels(self):
        res = classify_moisture_behaviour("Low Porosity")
        self.assertEqual(res["label"], "Low Porosity")
        
        res = classify_moisture_behaviour("Low") # Backward compat
        self.assertEqual(res["label"], "Low Porosity")

    def test_texture_new_labels(self):
        res = classify_texture("Spring curls")
        self.assertEqual(res["label"], "Type 3C — Spring Curls")
        self.assertIn("strong_definition", res["routine_flags"])
        
        res = classify_texture("Curly") # Backward compat
        self.assertEqual(res["label"], "Type 3")

    def test_humidity_response(self):
        res = classify_humidity_response("Expand and become frizzy")
        self.assertEqual(res["label"], "High Humidity Sensitivity")
        self.assertIn("anti_humectant", res["routine_flags"])

    def test_collate_advice_goals_first(self):
        answers = {
            "texture": "Soft waves",
            "density": "Thin",
            "moisture_behaviour": "High Porosity",
            "humidity_response": "Lose definition",
            "hair_goals": ["Volume", "Frizz control"]
        }
        
        advice = collateAdvice(answers)
        
        # Check goals
        self.assertEqual(advice["goals"], "Volume, Frizz control")
        
        # Check guardrails were processed
        self.assertIn("texture", advice["directives"])
        self.assertIn("density", advice["directives"])
        self.assertIn("moisture_behaviour", advice["directives"])
        self.assertIn("humidity_response", advice["directives"])
        
        # Check flags
        self.assertIn("avoid_heavy", advice["routine_flags"]["density"])
        self.assertIn("frizz_control", advice["routine_flags"]["humidity_response"])

if __name__ == '__main__':
    unittest.main()

