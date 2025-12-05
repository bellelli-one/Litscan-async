from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import time
import requests
from concurrent import futures

# Убедись, что адрес правильный (порт 8090)
MAIN_SERVICE_URL = "http://localhost:8090/api/analysebookscalc/"
SECRET_KEY = "secret12"

executor = futures.ThreadPoolExecutor(max_workers=2)

def calculate_canberra_similarity(target, book):
    """
    Считает схожесть.
    target - словарь с идеальными метриками.
    book - словарь с метриками книги.
    """
    # Ключи должны совпадать с тем, что приходит в JSON (snake_case)
    keys = ["avg_word_len", "lexical_diversity", "conjunction_freq", "avg_sentence_len"]
    distance = 0.0
    
    for k in keys:
        # float() нужен, чтобы защититься от None
        try:
            p = float(target.get(k, 0) or 0)
            q = float(book.get(k, 0) or 0)
        except (ValueError, TypeError):
            p, q = 0.0, 0.0
        
        if p + q == 0:
            term = 0
        else:
            term = abs(p - q) / (p + q)
            
        distance += term

    # 4 метрики -> макс расстояние 4. Нормируем к 1.
    dimensions = 4.0
    similarity = 1.0 - (distance / dimensions)
    return max(0.0, similarity)

def long_calculation_task(payload):
    try:
        app_id = payload.get("id")
        
        # === ИСПРАВЛЕНИЕ ЗДЕСЬ ===
        # Раньше было: target_vector = payload["target"]
        # Теперь собираем вручную из корня:
        target_vector = {
            "avg_word_len": payload.get("avg_word_len", 0),
            "lexical_diversity": payload.get("lexical_diversity", 0),
            "conjunction_freq": payload.get("conjunction_freq", 0),
            "avg_sentence_len": payload.get("avg_sentence_len", 0)
        }
        
        books_vectors = payload.get("books", [])
        
        print(f"Start analyzing app {app_id}. Books: {len(books_vectors)}")
        time.sleep(10) # Имитация работы
        
        if not books_vectors:
            return {"id": app_id, "data": {"status": 5, "probability": 0.0}}

        total_similarity = 0.0
        
        for book in books_vectors:
            sim = calculate_canberra_similarity(target_vector, book)
            total_similarity += sim
            
        avg_probability = total_similarity / len(books_vectors)
        print(f"App {app_id} match probability: {avg_probability:.2%}")

        final_status = 4 if avg_probability > 0.6 else 5

        # Формируем ответ для Go
        result = {
            "status": final_status,
            "response": f"Вероятность успеха: {avg_probability:.2%}", # <-- Отправляем результат
            # Если хочешь обновить текст response:
            # "response": f"Вероятность успеха: {avg_probability:.2%}"
        }
        
        return {"id": app_id, "data": result}
        
    except Exception as e:
        print(f"Error inside calculation task: {e}")
        # Возвращаем ошибку, чтобы хотя бы статус сменился (например, на rejected)
        return {"id": payload.get("id"), "data": {"status": 5}}

def task_callback(future):
    try:
        res = future.result()
        app_id = res["id"]
        data = res["data"]
        
        url = f"{MAIN_SERVICE_URL}{app_id}"
        headers = {
            "X-Secret-Key": SECRET_KEY,
            "Content-Type": "application/json"
        }
        
        response = requests.put(url, json=data, headers=headers)
        print(f"Sent callback to Go: {response.status_code}")
        
    except Exception as e:
        print(f"Callback error: {e}")

@api_view(['POST'])
def start_analysis(request):
    payload = request.data
    # Проверяем наличие основных полей
    if "id" in payload and "books" in payload:
        task = executor.submit(long_calculation_task, payload)
        task.add_done_callback(task_callback)
        return Response({"status": "Started"}, status=status.HTTP_200_OK)
    
    return Response({"error": "Missing id or books"}, status=status.HTTP_400_BAD_REQUEST)