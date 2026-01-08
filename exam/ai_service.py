from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def evaluate_answer(student_answer, correct_answer):
    """
    Evaluates descriptive answer using TF-IDF and cosine similarity
    Returns: (similarity_score, percentage, is_correct)
    """
    if not student_answer.strip() or not correct_answer.strip():
        return 0.0, 0.0, False
    
    # Convert answers to vectors
    corpus = [student_answer, correct_answer]
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(corpus)
    
    # Calculate similarity
    similarity = cosine_similarity(tfidf_matrix[0], tfidf_matrix[1])[0][0]
    score = round(similarity * 100, 2)
    is_correct = similarity > 0.5  # 50% threshold
    
    return similarity, score, is_correct
