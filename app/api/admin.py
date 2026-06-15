"""
内部管理接口
------------
提供模型健康度查看等运维功能。
生产环境应添加鉴权保护。
"""
from fastapi import APIRouter
from app.api.v1.chat import model_router

router = APIRouter(prefix="/admin")


@router.get("/model-health")
async def get_model_health():
    """查看所有模型的实时健康度数据"""
    health_data = {}
    for key, health in model_router.health_tracker.get_all().items():
        health_data[key] = {
            "provider": health.provider,
            "model_name": health.model_name,
            "success_rate": round(health.success_rate, 4),
            "load_rate": round(health.load_rate, 4),
            "health_score": round(health.health_score, 4),
            "avg_latency_ms": (
                round(health.avg_latency * 1000, 2)
                if health.avg_latency != float("inf")
                else None
            ),
            "current_load": health.current_load,
            "max_load": health.max_load,
            "total_requests": health.total,
            "success_count": health.success,
            "is_overloaded": health.is_overloaded,
        }
    return {"models": health_data, "count": len(health_data)}