from pydantic_ai import RunContext

from code_puppy.config import set_config_value, get_puppy_name
from code_puppy.messaging import emit_success, emit_error


def register_rename_puppy_tools(agent):
    @agent.tool
    def rename_puppy(context: RunContext, new_name: str) -> str:
        """
        Rename the puppy to a new name. This updates the puppy_name in the config file.
        
        Args:
            new_name: The new name for the puppy
            
        Returns:
            Success message with the new name
        """
        try:
            # Get the current name for the message
            old_name = get_puppy_name()
            
            # Validate the new name
            if not new_name or not new_name.strip():
                emit_error("Puppy name cannot be empty!")
                return "Error: Puppy name cannot be empty"
            
            # Clean up the name
            clean_name = new_name.strip()
            
            # Update the config
            set_config_value("puppy_name", clean_name)
            
            emit_success(f"🐶 Puppy renamed from '{old_name}' to '{clean_name}'! Woof woof!")
            return f"Successfully renamed puppy from '{old_name}' to '{clean_name}'"
            
        except Exception as e:
            emit_error(f"Failed to rename puppy: {str(e)}")
            return f"Error: Failed to rename puppy - {str(e)}"
