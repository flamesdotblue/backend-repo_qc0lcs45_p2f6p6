import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId
from datetime import datetime

from database import db, create_document, get_documents
from schemas import NGO, Campaign, Donation, Transaction, Receipt

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helpers

def oid_str(oid):
    return str(oid) if isinstance(oid, ObjectId) else oid


def serialize(doc):
    if not doc:
        return doc
    doc = dict(doc)
    if "_id" in doc:
        doc["_id"] = oid_str(doc["_id"])
    for k, v in list(doc.items()):
        if isinstance(v, ObjectId):
            doc[k] = oid_str(v)
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


@app.get("/")
def root():
    return {"message": "ParyavaranSahyog API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
        else:
            response["database"] = "❌ Not Available"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


@app.post("/api/seed")
def seed():
    # Seed NGOs and campaigns if empty
    if db["ngo"].count_documents({}) == 0:
        ngo_ids = []
        ngo_ids.append(db["ngo"].insert_one(NGO(name="Aranya Eco Foundation", registration_id="KA-REG-001", category="Air", city="Bengaluru", state="Karnataka", verified=True).model_dump()).inserted_id)
        ngo_ids.append(db["ngo"].insert_one(NGO(name="JalRaksha Trust", registration_id="KA-REG-002", category="Water", city="Bengaluru", state="Karnataka", verified=True).model_dump()).inserted_id)
        ngo_ids.append(db["ngo"].insert_one(NGO(name="Nirmal Waste Collective", registration_id="KA-REG-003", category="Waste", city="Bengaluru", state="Karnataka", verified=True).model_dump()).inserted_id)
        # campaigns
        db["campaign"].insert_many([
            Campaign(title="Air: Urban Tree Plantation", ngo_id=str(ngo_ids[0]), domain="Air", goal_inr=500000, description="Plant and maintain native trees in urban hotspots.").model_dump(),
            Campaign(title="Water: Lake Restoration", ngo_id=str(ngo_ids[1]), domain="Water", goal_inr=800000, description="Desilting and wetland buffer creation.").model_dump(),
            Campaign(title="Waste: Smart Segregation", ngo_id=str(ngo_ids[2]), domain="Waste", goal_inr=300000, description="IoT bins and community awareness.").model_dump(),
        ])
    return {"status": "ok"}


# NGOs
@app.get("/api/ngos")
def list_ngos():
    items = get_documents("ngo", {})
    return [serialize(x) for x in items]


@app.post("/api/ngos")
def create_ngo(ngo: NGO):
    new_id = create_document("ngo", ngo)
    return {"_id": new_id}


# Campaigns
@app.get("/api/campaigns")
def list_campaigns(domain: Optional[str] = None):
    filt = {"domain": domain} if domain else {}
    items = get_documents("campaign", filt)
    # join NGO names for ease
    ngo_map = {str(x["_id"]): x for x in db["ngo"].find()}
    out = []
    for it in items:
        s = serialize(it)
        ngo = ngo_map.get(s.get("ngo_id"))
        if ngo:
            s["ngo_name"] = ngo.get("name")
        out.append(s)
    return out


@app.post("/api/campaigns")
def create_campaign(c: Campaign):
    # Validate NGO exists
    ngo = db["ngo"].find_one({"_id": ObjectId(c.ngo_id)}) if ObjectId.is_valid(c.ngo_id) else None
    if not ngo:
        raise HTTPException(status_code=400, detail="NGO not found")
    new_id = create_document("campaign", c)
    return {"_id": new_id}


# Donations
@app.get("/api/donations")
def list_donations():
    items = get_documents("donation", {})
    return [serialize(x) for x in items]


class DonationIn(BaseModel):
    campaign_id: str
    donor_name: Optional[str] = None
    amount_inr: int
    payment_method: str


@app.post("/api/donations")
def create_donation(payload: DonationIn):
    # Validate campaign
    if not ObjectId.is_valid(payload.campaign_id):
        raise HTTPException(status_code=400, detail="Invalid campaign id")
    camp = db["campaign"].find_one({"_id": ObjectId(payload.campaign_id)})
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")

    donation = Donation(
        campaign_id=payload.campaign_id,
        donor_name=payload.donor_name,
        amount_inr=payload.amount_inr,
        payment_method=payload.payment_method,
    )
    donation_id = create_document("donation", donation)

    # Update campaign raised amount
    db["campaign"].update_one(
        {"_id": ObjectId(payload.campaign_id)},
        {"$inc": {"raised_inr": payload.amount_inr}, "$set": {"updated_at": datetime.utcnow()}},
    )

    # Simulate on-chain tx
    tx_hash = f"0x{ObjectId():x}"
    tx = Transaction(donation_id=donation_id, tx_hash=tx_hash, status="Settled")
    tx_id = create_document("transaction", tx)

    # Issue receipt
    receipt = Receipt(donation_id=donation_id, receipt_nft_id=f"nft-{donation_id}", issued_at=datetime.utcnow())
    receipt_id = create_document("receipt", receipt)

    return {
        "donation_id": donation_id,
        "tx_hash": tx_hash,
        "receipt_id": receipt_id,
        "message": "Donation recorded with on-chain receipt",
    }


# Ledger (transactions)
@app.get("/api/transactions")
def list_transactions(limit: int = 50):
    items = get_documents("transaction", {})
    items = items[-limit:]
    # join donation and campaign for context
    donation_map = {str(x["_id"]): x for x in db["donation"].find()}
    campaign_map = {str(x["_id"]): x for x in db["campaign"].find()}
    ngo_map = {str(x["_id"]): x for x in db["ngo"].find()}

    out = []
    for it in items[::-1]:  # newest first
        s = serialize(it)
        d = donation_map.get(s.get("donation_id"))
        if d:
            s["amount_inr"] = d.get("amount_inr")
            camp = campaign_map.get(d.get("campaign_id")) if d.get("campaign_id") else None
            if camp:
                s["campaign_title"] = camp.get("title")
                s["domain"] = camp.get("domain")
                ngo = ngo_map.get(camp.get("ngo_id")) if camp.get("ngo_id") else None
                if ngo:
                    s["ngo_name"] = ngo.get("name")
        out.append(s)
    return out


# Simple leaderboard
@app.get("/api/leaderboard")
def leaderboard():
    # aggregate eco points by NGO based on donations (1 point per 100 INR)
    pipeline = [
        {"$group": {"_id": "$campaign_id", "raised": {"$sum": "$amount_inr"}}},
    ]
    agg = list(db["donation"].aggregate(pipeline))
    camp_map = {str(x["_id"]): x for x in db["campaign"].find()}
    ngo_points = {}
    for row in agg:
        camp = camp_map.get(str(row["_id"]))
        if not camp:
            continue
        ngo_id = camp.get("ngo_id")
        ngo_points.setdefault(ngo_id, 0)
        ngo_points[ngo_id] += int(row["raised"]) // 100
    ngos = {str(x["_id"]): x for x in db["ngo"].find()}
    out = []
    for ngo_id, pts in sorted(ngo_points.items(), key=lambda kv: kv[1], reverse=True):
        name = ngos.get(ngo_id, {}).get("name", "Unknown NGO")
        out.append({"entity": name, "eco_points": pts})
    return out


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
