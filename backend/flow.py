import json
import json5
from pathlib import Path
from typing import Any, Literal, Callable, Optional

from crewai import Agent, Crew, Process, Task
from crewai.flow import Flow, and_, listen, router, start
from crewai_tools import SerperDevTool
from dotenv import load_dotenv
from pydantic import BaseModel

from sqlmodel import Session, select
# Assuming you have the engine and Job model in main.py
from main import engine, Job 

from schemas import (
    FinancialPlan,
    FinalBusinessPlan,
    GTMPlan,
    MarketReport,
    MVPPlan,
    ValidationResult,
)


PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")

SCHEMA_MAPPING: dict[str, type[BaseModel]] = {
    "validation_task": ValidationResult,
    "market_research_task": MarketReport,
    "product_architecture_task": MVPPlan,
    "financial_strategy_task": FinancialPlan,
    "gtm_strategy_task": GTMPlan,
    "synthesis_task": FinalBusinessPlan,
}

TOOL_FACTORIES = {
    "SerperDevTool": SerperDevTool,
}


def load_jsonc(filepath: Path) -> dict[str, Any]:
    return json5.loads(filepath.read_text(encoding="utf-8"))


def create_task_callback(job_id: str, task_name: str) -> Callable:
    """Creates a callback hook to save agent outputs to Postgres for SSE streaming."""
    def callback(task_output):
        with Session(engine) as session:
            job = session.exec(select(Job).where(Job.id == job_id)).first()
            if job:
                # Initialize JSONB dict if it is None
                if job.intermediate_outputs is None:
                    job.intermediate_outputs = {}
                
                # Append the output. CrewAI outputs have a json_dict property when using Pydantic
                try:
                    job.intermediate_outputs[task_name] = task_output.json_dict
                except AttributeError:
                    job.intermediate_outputs[task_name] = {"raw": str(task_output)}
                
                # Flag the JSONB column as modified so SQLAlchemy commits the change
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(job, "intermediate_outputs")
                
                session.add(job)
                session.commit()
    return callback


def run_task(task_name: str, inputs: dict[str, str], job_id: Optional[str] = None) -> BaseModel:
    crew_config = load_jsonc(PROJECT_DIR / "crew.jsonc")
    task_config = next(
        (task for task in crew_config["tasks"] if task["name"] == task_name),
        None,
    )
    if task_config is None:
        raise ValueError(f"No task named '{task_name}' in crew.jsonc")

    agent_name = task_config["agent"]
    agent_config = load_jsonc(PROJECT_DIR / "agents" / f"{agent_name}.jsonc")
    tool_names = agent_config.get("tools", [])
    unsupported_tools = set(tool_names) - TOOL_FACTORIES.keys()
    if unsupported_tools:
        raise ValueError(
            f"Agent '{agent_name}' configures unsupported tools: "
            f"{', '.join(sorted(unsupported_tools))}"
        )

    settings = agent_config.get("settings", {})
    agent = Agent(
        role=agent_config["role"],
        goal=agent_config["goal"],
        backstory=agent_config["backstory"],
        tools=[TOOL_FACTORIES[name]() for name in tool_names],
        llm=agent_config.get("llm"),
        allow_delegation=settings.get("allow_delegation", False),
        verbose=settings.get("verbose", False),
        planning=settings.get("planning", False),
    )
    
    task_schema = SCHEMA_MAPPING.get(task_name)
    if task_schema is None:
        raise ValueError(f"No output schema configured for task '{task_name}'")

    # Attach the callback if a job_id is provided
    task_callbacks = []
    if job_id:
        task_callbacks.append(create_task_callback(job_id, task_name))

    task = Task(
        name=task_name,
        description=task_config["description"],
        expected_output=task_config["expected_output"],
        agent=agent,
        output_pydantic=task_schema,
        callback=task_callbacks[0] if task_callbacks else None
    )
    
    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=crew_config.get("verbose", False),
        memory=False,
    )
    
    result = crew.kickoff(inputs=inputs)
    
    if result.pydantic is None:
        raise RuntimeError(
            f"Task '{task_name}' completed without the required "
            f"{task_schema.__name__} structured output."
        )
    return result.pydantic


class StartupWorkflowState(BaseModel):
    idea: str = ""
    job_id: Optional[str] = None
    validation: ValidationResult | None = None
    market_report: MarketReport | None = None
    product_plan: MVPPlan | None = None
    financial_plan: FinancialPlan | None = None
    gtm_plan: GTMPlan | None = None
    final_plan: FinalBusinessPlan | None = None


class StartupWorkflow(Flow[StartupWorkflowState]):
    @start()
    def validate_idea(self) -> ValidationResult:
        idea = self.state.idea.strip()
        if not idea:
            raise ValueError("A non-empty startup idea is required.")

        validation = run_task("validation_task", {"idea": idea}, self.state.job_id)
        if not isinstance(validation, ValidationResult):
            raise TypeError("validation_task returned an invalid result type.")
        self.state.validation = validation
        return validation

    @router(validate_idea)
    def route_validation(self) -> Literal["approved", "rejected"]:
        validation = self.state.validation
        if validation is None:
            raise RuntimeError("Validation result is missing.")
        return "approved" if validation.is_viable else "rejected"

    @listen("rejected")
    def return_rejection_report(self) -> dict[str, Any]:
        validation = self.state.validation
        if validation is None:
            raise RuntimeError("Validation result is missing.")
        return {
            "status": "rejected",
            "validation": validation.model_dump(mode="json"),
        }

    @listen("approved")
    def research_market(self) -> MarketReport:
        validation = self.state.validation
        if validation is None:
            raise RuntimeError("Validation result is missing.")
        result = run_task(
            "market_research_task",
            {
                "idea": self.state.idea,
                "validator_notes": validation.model_dump_json(indent=2),
            },
            self.state.job_id
        )
        if not isinstance(result, MarketReport):
            raise TypeError("market_research_task returned an invalid result type.")
        self.state.market_report = result
        return result

    @listen("approved")
    def define_product(self) -> MVPPlan:
        validation = self.state.validation
        if validation is None:
            raise RuntimeError("Validation result is missing.")
        result = run_task(
            "product_architecture_task",
            {
                "idea": self.state.idea,
                "validator_notes": validation.model_dump_json(indent=2),
            },
            self.state.job_id
        )
        if not isinstance(result, MVPPlan):
            raise TypeError(
                "product_architecture_task returned an invalid result type."
            )
        self.state.product_plan = result
        return result

    @listen(research_market)
    def plan_finances(self) -> FinancialPlan:
        market_report = self.state.market_report
        if market_report is None:
            raise RuntimeError("Market research report is missing.")
        result = run_task(
            "financial_strategy_task",
            {
                "idea": self.state.idea,
                "market_report": market_report.model_dump_json(indent=2),
            },
            self.state.job_id
        )
        if not isinstance(result, FinancialPlan):
            raise TypeError("financial_strategy_task returned an invalid result type.")
        self.state.financial_plan = result
        return result

    @listen(and_(research_market, define_product))
    def plan_go_to_market(self) -> GTMPlan:
        market_report = self.state.market_report
        product_plan = self.state.product_plan
        if market_report is None or product_plan is None:
            raise RuntimeError("Market or product report is missing.")
        result = run_task(
            "gtm_strategy_task",
            {
                "idea": self.state.idea,
                "market_report": market_report.model_dump_json(indent=2),
                "product_scope": product_plan.model_dump_json(indent=2),
            },
            self.state.job_id
        )
        if not isinstance(result, GTMPlan):
            raise TypeError("gtm_strategy_task returned an invalid result type.")
        self.state.gtm_plan = result
        return result

    @listen(and_(plan_finances, plan_go_to_market))
    def synthesize_business_plan(self) -> FinalBusinessPlan:
        validation = self.state.validation
        market_report = self.state.market_report
        product_plan = self.state.product_plan
        financial_plan = self.state.financial_plan
        gtm_plan = self.state.gtm_plan
        if (
            validation is None
            or market_report is None
            or product_plan is None
            or financial_plan is None
            or gtm_plan is None
        ):
            raise RuntimeError("One or more reports required for synthesis are missing.")

        result = run_task(
            "synthesis_task",
            {
                "idea": self.state.idea,
                "validation_report": validation.model_dump_json(indent=2),
                "market_report": market_report.model_dump_json(indent=2),
                "product_scope": product_plan.model_dump_json(indent=2),
                "financial_report": financial_plan.model_dump_json(indent=2),
                "gtm_report": gtm_plan.model_dump_json(indent=2),
            },
            self.state.job_id
        )
        if not isinstance(result, FinalBusinessPlan):
            raise TypeError("synthesis_task returned an invalid result type.")
        self.state.final_plan = result
        return result


def run_startup_workflow(raw_idea: str, job_id: Optional[str] = None) -> FinalBusinessPlan | dict[str, Any]:
    flow = StartupWorkflow()
    # Explicitly set the job_id in the state so it cascades through the flow
    if job_id:
        flow.state.job_id = job_id
    return flow.kickoff(inputs={"idea": raw_idea})


def kickoff() -> None:
    idea = input("Enter a startup idea: ").strip()
    if not idea:
        raise ValueError("A non-empty startup idea is required.")
    result = run_startup_workflow(idea)
    if isinstance(result, BaseModel):
        print(result.model_dump_json(indent=2))
    else:
        print(json.dumps(result, indent=2))


def plot() -> None:
    StartupWorkflow().plot("startup_workflow")


if __name__ == "__main__":
    kickoff()