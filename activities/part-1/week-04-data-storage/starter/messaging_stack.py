"""
Regla de EventBridge programada → Lambda de ingesta (opcional).

Nota: en AWS EventBridge, las expresiones rate() tienen un mínimo de 1 minuto;
no existe schedule oficial de 5 segundos. Aquí se usa 1 minuto deshabilitado
por defecto, como en la práctica habitual de despliegue.
"""
from __future__ import annotations

from typing import Optional

from aws_cdk import Duration, Stack, aws_events as events, aws_events_targets as targets
from aws_cdk import aws_lambda as lambda_
from constructs import Construct


class MessagingStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        ingest_function: Optional[lambda_.IFunction] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.ingest_rule = events.Rule(
            self,
            "IngestScheduleRule",
            schedule=events.Schedule.rate(Duration.minutes(1)),
            enabled=False,
        )
        if ingest_function is not None:
            self.ingest_rule.add_target(targets.LambdaFunction(ingest_function))
