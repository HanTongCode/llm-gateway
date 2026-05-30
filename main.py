import uvicorn
from gateway.app import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run("main:app", host='localhost', port=8000, reload=True)
    print("路由列表：", [r.path for r in app.routes])