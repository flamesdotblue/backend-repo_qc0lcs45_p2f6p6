from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

# Each model name will map to a collection (lowercased)

class NGO(BaseModel):
    name: str = Field(..., description="Legal name of the NGO")
    registration_id: str = Field(..., description="Govt registration ID")
    category: str = Field(..., description="Air | Water | Waste | Multi")
    city: Optional[str] = Field(None, description="City of operation")
    state: Optional[str] = Field(None, description="State/UT of operation")
    verified: bool = Field(default=False, description="Verification status")

class Campaign(BaseModel):
    title: str
    ngo_id: str = Field(..., description="Reference to NGO _id as string")
    domain: str = Field(..., description="Air | Water | Waste")
    goal_inr: int = Field(..., ge=1)
    raised_inr: int = Field(default=0, ge=0)
    description: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    milestones: Optional[List[str]] = None

class Donation(BaseModel):
    campaign_id: str
    donor_name: Optional[str] = Field(None, description="Optional donor display name")
    amount_inr: int = Field(..., ge=1)
    payment_method: str = Field(..., description="upi | crypto | card | other")

class Transaction(BaseModel):
    donation_id: str
    tx_hash: str
    status: str = Field(default="Settled", description="Settled | Escrow | Pending")

class Receipt(BaseModel):
    donation_id: str
    receipt_nft_id: Optional[str] = None
    issued_at: Optional[datetime] = None

# Model for leaderboard aggregation response (not stored as a separate collection)
class LeaderboardItem(BaseModel):
    entity: str
    eco_points: int

model_config = ConfigDict(extra='ignore')
