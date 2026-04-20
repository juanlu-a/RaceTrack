"""
Week 4: Data Storage — CDK Stack

DynamoDB: f1_sessions, f1_driver_stats. S3: datos crudos de la API.
"""
from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
)
from constructs import Construct


class DataStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        self.sessions_table = dynamodb.Table(
            self,
            "F1Sessions",
            table_name="f1_sessions",
            partition_key=dynamodb.Attribute(
                name="session_key", type=dynamodb.AttributeType.NUMBER
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.driver_stats_table = dynamodb.Table(
            self,
            "F1DriverStats",
            table_name="f1_driver_stats",
            partition_key=dynamodb.Attribute(
                name="session_key", type=dynamodb.AttributeType.NUMBER
            ),
            sort_key=dynamodb.Attribute(
                name="driver_number", type=dynamodb.AttributeType.NUMBER
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.raw_data_bucket = s3.Bucket(
            self,
            "F1RawData",
            bucket_name="f1-raw-data",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )
