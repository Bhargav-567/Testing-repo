from dataclasses import dataclass
from typing import List, Dict, Tuple, Set, Optional
import re
import spacy
from sentence_transformers import SentenceTransformer, util
import numpy as np
import math

# ==============================
# DATA STRUCTURES (MINIMAL)
# ==============================
@dataclass
class Concept:
    name: str
    keywords: List[str]
    weight: float = 1.0

@dataclass
class QuestionConfig:
    question_id: str
    type: str          # NEW: REQUIRED
    teacher_answer: str = ""  # Descriptive only
    correct_option: str = ""  # MCQ only  
    correct_answer: str = ""  # Fallback
    concepts: List[Concept] = None
    max_score: float = 1.0
    
# ==============================
# NEW AI-SERVICE DESCRIPTIVE GRADER
# ==============================
class DescriptiveAnswerGrader:
    def __init__(
        self,
        emb_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        w_concept: float = 0.25,    # Reduced for balance
        w_relation: float = 0.30,
        w_semantic: float = 0.35,   # Increased (transformer core)
        w_penalty: float = 0.10,
    ):
        self.model = SentenceTransformer(emb_model_name)
        self.nlp = spacy.load("en_core_web_sm")
        self.w_concept = w_concept
        self.w_relation = w_relation
        self.w_semantic = w_semantic
        self.w_penalty = w_penalty

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.lower()).strip()

    def compute_concept_score(self, cfg: QuestionConfig, student_answer: str) -> float:
        if not cfg.concepts:
            return 1.0
        text = self._normalize(student_answer)
        total_weight = sum(c.weight for c in cfg.concepts)
        if total_weight == 0: return 0.0
        gained = 0.0
        for c in cfg.concepts:
            for kw in c.keywords:
                if kw.lower() in text:
                    gained += c.weight
                    break
        return gained / total_weight

    def extract_relations(self, text: str, concepts: List[Concept]) -> Set[Tuple[str, str, str]]:
        if not concepts: return set()
        doc = self.nlp(text)
        keyword_to_concept = {kw.lower(): c.name for c in concepts for kw in c.keywords}
        relations: Set[Tuple[str, str, str]] = set()
        for token in doc:
            if token.pos_ != "VERB": continue
            verb = token.lemma_.lower()
            subj = obj = None
            for child in token.children:
                key = child.lemma_.lower()
                if child.dep_ in ("nsubj", "nsubjpass") and key in keyword_to_concept:
                    subj = keyword_to_concept[key]
                if child.dep_ in ("dobj", "pobj", "attr", "dative", "oprd") and key in keyword_to_concept:
                    obj = keyword_to_concept[key]
            if subj and obj:
                relations.add((subj, verb, obj))
        return relations

    def compute_relation_score(self, cfg: QuestionConfig, student_answer: str) -> float:
        concepts = cfg.concepts or []
        teacher_rels = self.extract_relations(self._normalize(cfg.teacher_answer), concepts)
        student_rels = self.extract_relations(self._normalize(student_answer), concepts)
        if not teacher_rels: return 1.0
        matches = sum(1 for rel in teacher_rels if rel in student_rels)
        return matches / len(teacher_rels)

    def compute_semantic_similarity(self, teacher_answer: str, student_answer: str) -> float:
        """NEW: Transformer replaces TF-IDF"""
        emb_t = self.model.encode(teacher_answer, convert_to_tensor=True)
        emb_s = self.model.encode(student_answer, convert_to_tensor=True)
        sim = util.cos_sim(emb_t, emb_s).item()
        sim = max(-1.0, min(1.0, sim))
        # Nonlinear scale for realistic grading
        floor, exp = 0.05, 1.1
        if sim < floor: return 0.0
        scaled = (sim - floor) / (1.0 - floor)
        return math.pow(scaled, exp)

    def compute_penalty(self, cfg: QuestionConfig, student_answer: str) -> float:
        text = self._normalize(student_answer)
        doc = self.nlp(text)
        # Keyword stuffing
        concept_kws = [kw.lower() for c in (cfg.concepts or []) for kw in c.keywords]
        word_freq = {t.lemma_.lower(): doc.count_by("LEMMA", t.lemma_) for t in doc if t.is_alpha}
        rep_hits = sum(1 for kw in concept_kws if word_freq.get(kw, 0) > 3)
        # Noun/verb ratio
        noun_cnt = sum(1 for t in doc if t.pos_ in ("NOUN", "PROPN"))
        verb_cnt = sum(1 for t in doc if t.pos_ == "VERB")
        ratio_pen = 0.5 if verb_cnt == 0 and noun_cnt > 0 else 0.3 if noun_cnt / max(1, verb_cnt) > 5 else 0.0
        # Length rambling
        t_len = len(self._normalize(cfg.teacher_answer).split())
        s_len = len(text.split())
        len_pen = 0.4 if t_len > 0 and s_len > 3 * t_len else 0.0
        raw_pen = min(0.5, 0.2 * rep_hits) + ratio_pen + len_pen
        return max(0.0, min(1.0, raw_pen))

    def evaluate_answer(student_answer, correct_answer, concepts=None, max_score=10.0):
        """NEW: Hybrid wrapper for backward compatibility"""
        grader = DescriptiveAnswerGrader()
        cfg = QuestionConfig("Q1", correct_answer, concepts or [], max_score)
        result = grader.grade(cfg, student_answer)
        similarity = result["normalized"]  # 0-1.0
        ai_score = (similarity * 100)  # Percentage
        is_correct = similarity > 0.5
        return similarity, ai_score, is_correct

    def grade(self, cfg: QuestionConfig, student_answer: str) -> Dict:
        """Full breakdown (for debugging)"""
        c_score = self.compute_concept_score(cfg, student_answer)
        r_score = self.compute_relation_score(cfg, student_answer)
        s_score = self.compute_semantic_similarity(cfg.teacher_answer, student_answer)
        penalty = self.compute_penalty(cfg, student_answer)
        
        combined = (self.w_concept * c_score + 
                   self.w_relation * r_score + 
                   self.w_semantic * s_score - 
                   self.w_penalty * penalty)
        combined = max(0.0, min(1.0, combined))
        final_score = combined * cfg.max_score
        
        return {
            "final_score": final_score,
            "normalized": combined,
            "concept_score": c_score,
            "relation_score": r_score,
            "semantic_similarity": s_score,  # NEW transformer component
            "penalty": penalty,
        }

# ==============================
# USAGE (Direct replacement)
# ==============================
if __name__ == "__main__":
    grader = DescriptiveAnswerGrader()
    
    student = "Plants use light to make sugar."
    teacher = "Plants use sunlight to produce glucose."
    
    # SAME API as old TF-IDF
    sim, perc, correct = grader.evaluate_answer(student, teacher)
    print(f"Similarity: {sim:.3f}, Score: {perc}%, Correct: {correct}")
    
    # Full breakdown
    concepts = [Concept("plants", ["plant", "plants"]), Concept("sunlight", ["sunlight", "light"])]
    cfg = QuestionConfig("Q1", teacher, concepts, 10.0)
    print(grader.grade(cfg, student))
