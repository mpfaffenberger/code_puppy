"""Hermes-style governance plugin for Code Puppy.

Ports the self-improving-skills governance loop from NousResearch's Hermes
agent into Code Puppy as a plugin:

* A per-session **tool budget gate** (onboarding cap -> unlock after a skill
  action -> expanded cap), modelled on Hermes' ``IterationBudget``.
* **Skill nudges** that remind the agent to capture reusable workflows as
  skills, modelled on Hermes' ``SKILLS_GUIDANCE``.
* A ``skill_manage`` tool (create/patch/view/list/archive) that writes
  ``SKILL.md`` files into the agent_skills store.

Enforcement is **opt-in**: the plugin loads quiet and does nothing until the
user arms it with ``/budget on`` (or sets ``hermes_governance_enabled=true``).
"""
