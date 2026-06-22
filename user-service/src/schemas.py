from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, EmailStr, Field, ConfigDict

class UserBase(BaseModel):
    email: EmailStr = Field(..., description="The primary email address of the user")
    username: str = Field(..., min_length=3, max_length=50, description="Unique username within the tenant")
    full_name: Optional[str] = Field(None, max_length=100, description="Full name of the user")
    is_active: bool = Field(default=True, description="Whether the user account is active")
    tenant_id: str = Field(..., description="The tenant identifier for multi-tenancy isolation")

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, description="Plain text password for the user")

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = Field(None, description="Updated email address")
    username: Optional[str] = Field(None, min_length=3, max_length=50, description="Updated username")
    full_name: Optional[str] = Field(None, max_length=100, description="Updated full name")
    is_active: Optional[bool] = Field(None, description="Updated active status")
    password: Optional[str] = Field(None, min_length=8, description="Updated password")

class UserResponse(UserBase):
    id: int = Field(..., description="The unique database identifier of the user")
    created_at: datetime = Field(..., description="Timestamp when the user was created")
    updated_at: datetime = Field(..., description="Timestamp when the user was last updated")

    model_config = ConfigDict(from_attributes=True)

class UserContext(BaseModel):
    """
    Schema representing the user context returned by the FastMCP tool 'get_user_context'.
    """
    user_id: int = Field(..., description="The unique identifier of the user")
    tenant_id: str = Field(..., description="The tenant identifier")
    username: str = Field(..., description="The username")
    email: EmailStr = Field(..., description="The email address")
    is_active: bool = Field(..., description="Active status of the user")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional contextual metadata for the user")
    retrieved_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp when this context was retrieved")

    model_config = ConfigDict(from_attributes=True)