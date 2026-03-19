"""Experiment manager — creates and manages A/B experiments on trigger variables."""

from __future__ import annotations

import logging
import random

from growthclaw.models.experiment import Experiment, ExperimentArm
from growthclaw.models.trigger import TriggerRule

logger = logging.getLogger("growthclaw.experiments.manager")


def create_delay_experiment(trigger: TriggerRule) -> Experiment:
    """Create a delay timing experiment for a trigger.

    Tests 3 arms: short, medium, and long delay.
    """
    base_delay = trigger.delay_minutes
    arms = [
        ExperimentArm(name="short", value=max(5, base_delay // 2)),
        ExperimentArm(name="medium", value=base_delay),
        ExperimentArm(name="long", value=base_delay * 2),
    ]

    experiment = Experiment(
        name=f"{trigger.name}_delay_test",
        trigger_id=trigger.id,
        variable="delay_minutes",
        arms=arms,
        metric="conversion_rate",
    )

    logger.info(
        "Created experiment '%s': arms=%s",
        experiment.name,
        [(a.name, a.value) for a in arms],
    )
    return experiment


def assign_arm(experiment: Experiment) -> ExperimentArm:
    """Randomly assign a user to an experiment arm."""
    arm = random.choice(experiment.arms)  # noqa: S311
    logger.debug("Assigned arm '%s' (value=%s) for experiment '%s'", arm.name, arm.value, experiment.name)
    return arm


def get_delay_for_arm(arm: ExperimentArm) -> int:
    """Get the delay in minutes for an experiment arm."""
    return int(arm.value)
