def find_porosity_score(answers):
    score = 0

    for answer in answers:
        if answer == 'B':
            score += 1
        elif answer == 'C':
            score += 2
    # Determine porosity level based on score
    if score <= 3:
        return 'Low Porosity'
    
    # Use the concise chained comparison for elegance and correctness
    elif 3 < score <= 6:
        return 'Medium Porosity' 
    
    # Any score 7 or above is High Porosity (up to 10)
    else:
        return "High Porosity"



# # Score 0 (All Low Porosity 'A's)
# test_low = find_porosity_score(['A', 'A', 'A', 'A', 'A'])
# # Score 5 (All Medium Porosity 'B's)
# test_medium = find_porosity_score(['B', 'B', 'B', 'B', 'B'])
# # Score 10 (All High Porosity 'C's)
# test_high = find_porosity_score(['C', 'C', 'C', 'C', 'C'])
# # Score 4 (e.g., [A, C, B, B, A] -> 0+2+1+1+0 = 4)
# test_mixed = find_porosity_score(['A', 'C', 'B', 'B', 'A']) 

# print(f"Test Low (Score 0): {test_low}")       
# print(f"Test Medium (Score 5): {test_medium}")  
# print(f"Test High (Score 10): {test_high}")      
# print(f"Test Mixed (Score 4): {test_mixed}")    