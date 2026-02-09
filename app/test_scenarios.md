User: "My hair has been breaking a lot lately"
Expected: Empath asks about when this happens (wet/dry, brushing, etc.)
User: "Mostly when I brush it dry"
Expected: Empath asks about wash day timeline
User: "It's day 3 after washing"
Expected: Empath summarizes and triggers [CHECKPOINT: BREAKAGE]
Test Scenario 2: Moisture Issue
User: "My hair feels really dry and rough"
Expected: Empath asks clarifying questions about texture
User: "It feels like straw, especially at the ends"
Expected: Empath asks about wash day
User: "I washed it yesterday"
Expected: Empath summarizes and triggers [CHECKPOINT: MOISTURE]
Test Scenario 3: Scalp Issue (Testing Accessible Language)
User: "My scalp has been really itchy"
Expected: Empath asks about redness, oil, or other symptoms (using "irritation" not "inflammation")
User: "Yes, it's red and a bit flaky"
Expected: Empath asks about wash day
User: "It's been 5 days since I washed"
Expected: Empath summarizes and triggers [CHECKPOINT: SCALP]
Test Scenario 4: Definition Issue
User: "My curls look messy and undefined"
Expected: Empath asks if hair feels healthy or dry
User: "It feels soft and healthy, just not defined"
Expected: Empath asks about wash day
User: "Day 2 after washing"
Expected: Empath summarizes and triggers [CHECKPOINT: DEFINITION]