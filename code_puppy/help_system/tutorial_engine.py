"""Tutorial engine for interactive learning guides."""

from typing import Dict, Optional

TUTORIALS: Dict[str, Dict] = {
    "basics": {
        "title": "Introduction to Code Puppy",
        "description": "Learn the basics in 5 minutes",
        "steps": [
            {
                "title": "What is Code Puppy?",
                "content": "Code Puppy is an AI-powered coding assistant that helps you write, understand, and improve code.",
                "action": None,
            },
            {
                "title": "Your First Command",
                "content": "Try /help to see all available commands.",
                "action": "type: /help",
            },
            {
                "title": "Switching Models",
                "content": "Use /model to choose which AI model powers your responses.",
                "action": "type: /model",
            },
            {
                "title": "Switching Agents",
                "content": "Use /agent to switch between specialized coding assistants.",
                "action": "type: /agent",
            },
            {
                "title": "You're Ready!",
                "content": "You now know the basics! Use /help anytime for guidance.",
                "action": None,
            },
        ],
    },
    "agents": {
        "title": "Working with Agents",
        "description": "Learn how to use and create agents",
        "steps": [
            {
                "title": "What are Agents?",
                "content": "Agents are specialized AI assistants with different personalities, tools, and knowledge.",
                "action": None,
            },
            {
                "title": "View Available Agents",
                "content": "Type /agent to see all available agents and their capabilities.",
                "action": "type: /agent",
            },
            {
                "title": "Switch Agents",
                "content": "Type /agent <name> to switch to a specific agent.",
                "action": "type: /agent code-puppy",
            },
            {
                "title": "See Agent Tools",
                "content": "Type /tools to see what tools the current agent has access to.",
                "action": "type: /tools",
            },
        ],
    },
    "models": {
        "title": "Working with Models",
        "description": "Learn how to select and configure AI models",
        "steps": [
            {
                "title": "What are Models?",
                "content": "Models are the AI systems that generate responses. Different models have different strengths.",
                "action": None,
            },
            {
                "title": "View Available Models",
                "content": "Type /model to see and select from available models.",
                "action": "type: /model",
            },
            {
                "title": "Add New Models",
                "content": "Type /add_model to browse and add models from models.dev.",
                "action": "type: /add_model",
            },
            {
                "title": "Configure Models",
                "content": "Type /model_settings to fine-tune model parameters like temperature.",
                "action": "type: /model_settings",
            },
        ],
    },
}


class TutorialEngine:
    """Engine for running interactive tutorials."""

    def __init__(self):
        self.tutorials = TUTORIALS

    def list_tutorials(self) -> str:
        """List available tutorials."""
        output = "Available tutorials:\n\n"
        for name, tutorial in self.tutorials.items():
            output += f"  {name:20} {tutorial['description']}\n"
        output += "\nUsage: /help tutorial <topic>"
        return output

    def get_tutorial(self, topic: str) -> Optional[Dict]:
        """Get a tutorial by topic."""
        return self.tutorials.get(topic)

    def format_tutorial(self, topic: str) -> str:
        """Format a tutorial for display."""
        tutorial = self.tutorials.get(topic)
        if not tutorial:
            return f"Tutorial not found: {topic}\n\nAvailable: {', '.join(self.tutorials.keys())}"

        output = f"\nTutorial: {tutorial['title']}\n"
        output += "=" * 40 + "\n\n"
        output += f"{tutorial['description']}\n\n"

        for i, step in enumerate(tutorial["steps"], 1):
            output += f"Step {i}/{len(tutorial['steps'])}: {step['title']}\n"
            output += "-" * 30 + "\n"
            output += f"  {step['content']}\n"
            if step.get("action"):
                output += f"  Action: {step['action']}\n"
            output += "\n"

        output += "Tutorial complete! You're ready to use Code Puppy."
        return output
