from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException, status, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from datetime import datetime
from jose import JWTError, jwt
from passlib.context import CryptContext
import uuid
import os
from fastapi.middleware.cors import CORSMiddleware

# Security settings
SECRET_KEY = os.urandom(24).hex()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./messenger.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True)
    hashed_password = Column(String)
    
class Chat(Base):
    __tablename__ = "chats"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String)
    messages = relationship("Message", back_populates="chat")

class Message(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    chat_id = Column(String, ForeignKey("chats.id"))
    user_id = Column(String, ForeignKey("users.id"))
    chat = relationship("Chat", back_populates="messages")
    user = relationship("User")

Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Security setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

# Create default data
def create_default_data():
    db = SessionLocal()
    try:
        if not db.query(User).first():
            default_users = [
                {"username": "arudenaytsan", "password": "gdbHDJ231D"},
                {"username": "klementevyp", "password": "jhbsfHBD7213"}
            ]
            
            for user_data in default_users:
                hashed_password = get_password_hash(user_data["password"])
                user = User(username=user_data["username"], hashed_password=hashed_password)
                db.add(user)
            
            default_chats = ["Sweet Home"]
            for chat_name in default_chats:
                if not db.query(Chat).filter(Chat.name == chat_name).first():
                    chat = Chat(name=chat_name)
                    db.add(chat)
            
            db.commit()
    finally:
        db.close()

# FastAPI app
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="static")

# WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.user_chat_map: Dict[str, str] = {}  # username -> chat_id

    async def connect(self, websocket: WebSocket, chat_id: str, username: str):
        await websocket.accept()
        
        # Удаляем пользователя из предыдущего чата, если он был
        if username in self.user_chat_map:
            old_chat = self.user_chat_map[username]
            if old_chat in self.active_connections:
                for conn in list(self.active_connections[old_chat]):
                    if getattr(conn, "username", None) == username:
                        self.active_connections[old_chat].remove(conn)
        
        # Добавляем в новый чат
        if chat_id not in self.active_connections:
            self.active_connections[chat_id] = set()
        
        self.active_connections[chat_id].add(websocket)
        self.user_chat_map[username] = chat_id
        setattr(websocket, "username", username)
        setattr(websocket, "chat_id", chat_id)
        
        await self.broadcast_online_count(chat_id)

    async def disconnect(self, websocket: WebSocket):
        username = getattr(websocket, "username", None)
        chat_id = getattr(websocket, "chat_id", None)
        
        if chat_id and chat_id in self.active_connections:
            self.active_connections[chat_id].discard(websocket)
        
        if username and username in self.user_chat_map:
            del self.user_chat_map[username]
        
        if chat_id:
            await self.broadcast_online_count(chat_id)

    async def broadcast_online_count(self, chat_id: str):
        if chat_id not in self.active_connections:
            return
            
        online_users = set()
        for conn in self.active_connections[chat_id]:
            if hasattr(conn, "username"):
                online_users.add(conn.username)
        
        message = {
            "type": "online_count",
            "count": len(online_users),
            "users": list(online_users)
        }
        
        await self.broadcast(message, chat_id)

    async def broadcast(self, message: dict, chat_id: str):
        if chat_id not in self.active_connections:
            return
            
        for connection in self.active_connections[chat_id]:
            try:
                await connection.send_json(message)
            except:
                await self.disconnect(connection)

manager = ConnectionManager()

# Auth endpoints
@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

# Chat endpoints
@app.get("/messages/{chat_id}")
async def get_messages(chat_id: str, db: Session = Depends(get_db), 
                      user: User = Depends(get_current_user)):
    messages = db.query(Message).filter(Message.chat_id == chat_id)\
                .order_by(Message.timestamp.asc()).all()
    return [
        {
            "content": msg.content,
            "username": msg.user.username,
            "timestamp": msg.timestamp.isoformat()
        } for msg in messages
    ]

# Main endpoints
@app.get("/")
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/validate-token")
async def validate_token(user: User = Depends(get_current_user)):
    return {"status": "valid"}

@app.websocket("/ws/{chat_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    chat_id: str,
    token: str,
    db: Session = Depends(get_db)
):
    try:
        user = get_current_user(token, db)
        await manager.connect(websocket, chat_id, user.username)
        try:
            while True:
                data = await websocket.receive_text()
                message = Message(
                    content=data,
                    chat_id=chat_id,
                    user_id=user.id
                )
                db.add(message)
                db.commit()
                await manager.broadcast({
                    "type": "message",
                    "content": data,
                    "username": user.username,
                    "timestamp": datetime.utcnow().isoformat()
                }, chat_id)
        except WebSocketDisconnect:
            await manager.disconnect(websocket)
        finally:
            db.close()
    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)

# Create default data on startup
create_default_data()