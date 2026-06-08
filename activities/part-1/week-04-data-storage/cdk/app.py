#!/usr/bin/env python3
"""
Punto de entrada CDK para la semana 4. Ejecutar desde esta carpeta:

    pip install -r requirements.txt
    cdk synth
"""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "starter"))

import aws_cdk as cdk

from data_stack import DataStack
from messaging_stack import MessagingStack

app = cdk.App()
_env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

DataStack(app, "RaceTrackDataStack", env=_env)
MessagingStack(app, "RaceTrackMessagingStack", env=_env)

app.synth()
