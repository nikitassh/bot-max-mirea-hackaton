from fastapi import FastAPI
from api.routers import tickets, health

app = FastAPI(title="Ticket Bot API", version="1.0.0")
app.include_router(health.router)
app.include_router(tickets.router, prefix="/tickets")
