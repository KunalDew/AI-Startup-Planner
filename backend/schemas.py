from pydantic import BaseModel, Field
from typing import List, Optional

# 1. Validator Schema
class ValidationResult(BaseModel):
    is_viable: bool = Field(..., description="True if the idea passes validation, False otherwise.")
    score: int = Field(..., ge=0, le=100, description="Score from 0 to 100 based on problem-solution fit.")
    critique: str = Field(..., description="Detailed explanation of the decision, including saturation checks.")

# 2. Market Research Schema
class Competitor(BaseModel):
    name: str
    differentiator: str
    pricing_url: Optional[str]

class MarketReport(BaseModel):
    tam_sam_som_analysis: str = Field(..., description="TAM/SAM/SOM sizing including methodology (top-down/bottom-up) and specific URLs.")
    competitors: List[Competitor]
    target_demographics: str = Field(..., description="Primary user personas and geographic focus.")
    sources_cited: List[str] = Field(..., description="Mandatory list of all URLs and sources used for market data.")

# 3. Product Architect Schema
class MVPPlan(BaseModel):
    core_features: List[str] = Field(..., description="Strict list of features required for the Minimum Viable Product.")
    user_journeys: str = Field(..., description="Step-by-step flow of the primary user interaction.")
    technical_feasibility: str = Field(..., description="Hardware/software constraints and proposed tech stack.")

# 4. Financial Strategy Schema
class PricingTier(BaseModel):
    tier_name: str
    price: float
    description: str

class FinancialPlan(BaseModel):
    capital_requirements: str = Field(..., description="Estimated initial funding required to build the MVP.")
    unit_economics: str = Field(..., description="Projected Customer Acquisition Cost (CAC) vs Lifetime Value (LTV).")
    pricing_tiers: List[PricingTier]
    assumptions: List[str] = Field(..., description="Explicit list of assumptions made to calculate these financials.")

# 5. Go-To-Market Schema
class GTMPlan(BaseModel):
    acquisition_channels: List[str] = Field(..., description="Initial channels for customer acquisition (e.g., SEO, Paid Social).")
    brand_positioning: str = Field(..., description="Core value proposition and brand messaging.")
    launch_timeline: str = Field(..., description="Phased timeline from MVP launch to early scaling.")

# 6. Final Executive Summary Schema
class FinalBusinessPlan(BaseModel):
    executive_summary: str
    validation_notes: ValidationResult
    market_analysis: MarketReport
    product_roadmap: MVPPlan
    financial_projections: FinancialPlan
    go_to_market_strategy: GTMPlan