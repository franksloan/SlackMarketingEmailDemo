from dataclasses import dataclass, field


@dataclass
class EvalCase:
    id: str
    brief: str
    description: str
    # Set True when the pipeline should stop and ask the user a question
    expect_clarification: bool = False
    # Audience IDs that MUST appear in the plan (subset match)
    expected_audience_ids: list[str] = field(default_factory=list)


CASES: list[EvalCase] = [
    EvalCase(
        id="s3_engineers",
        brief="Write a marketing email about Amazon S3 targeting software engineers and solutions architects",
        description="Valid brief — product and engineering audience explicit",
        expected_audience_ids=["eng_lead_sa"],
    ),
    EvalCase(
        id="ec2_cto",
        brief="Create a campaign email for Amazon EC2 aimed at CTOs and technology officers",
        description="Valid brief — CTO audience explicit",
        expected_audience_ids=["cto"],
    ),
    EvalCase(
        id="aurora_pm",
        brief="Write a product-led email campaign for Amazon Aurora targeting product managers and CPOs focused on roadmap and portfolio",
        description="Valid brief — product manager audience",
        expected_audience_ids=["cpo_pm"],
    ),
    EvalCase(
        id="sagemaker_multi",
        brief="Create an AWS SageMaker email campaign for engineers, solutions architects, and CTOs",
        description="Valid brief — multiple audiences",
        expected_audience_ids=["eng_lead_sa", "cto"],
    ),
    EvalCase(
        id="no_audience",
        brief="Write an email about Amazon Redshift",
        description="No audience keyword — should ask user to specify audience",
        expect_clarification=True,
    ),
    EvalCase(
        id="no_product",
        brief="Write a marketing email for CTOs",
        description="No AWS product mentioned — should ask user to specify product",
        expect_clarification=True,
    ),
    EvalCase(
        id="vague",
        brief="Write a marketing email",
        description="No product and no audience — should ask user to clarify",
        expect_clarification=True,
    ),
]
