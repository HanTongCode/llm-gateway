import requests

res = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "你好"}],
        "stream": True
    },
    stream=True
)

print("状态码:", res.status_code)
print("---")
for line in res.iter_lines():
    if line:
        print(line.decode("utf-8"))