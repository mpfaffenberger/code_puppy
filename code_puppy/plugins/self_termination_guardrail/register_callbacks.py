"""Callback registration for the self termination command guard plugin.

Hooks into the run_shell_command phase to intercept destructive shell
commands (kill, pkill, killall, Stop-Process, Taskkill) 
Any command detected will be blocked immediatly

"""

from code_puppy.callbacks import register_callback

from code_puppy.plugins.self_termination_guardrail.detector import (
    detect_self_termination_command,
)

from code_puppy.plugins.guard_framework import(
    make_shell_guard,
    GuardSpec,
)

_DESTRUCTIVE_GUARD_SPEC = GuardSpec(                                                                                                                                                                                                            
    title="Self Termination Command Guard ",                                                                                                                                                                                                         
    detected_label="Self termination command detected: ",                                                                                                                                                                                             
    consequence="This command could terminate the code-puppy process currently running",                                                                                                                                                                             
    block_advice="If you need to close code-puppy simple type 'exit' or close out of the terminal using the red button in the top left",                                                                                                                                                             
    detect=detect_self_termination_command,                                                                                                                                                                                                          
)                                                                                                                                                                                                                                               
                                                                                                                                                                                                                                                
self_termination_command_callback = make_shell_guard(_DESTRUCTIVE_GUARD_SPEC)  

def register() -> None:                                                                                                                                                                                                                 
    register_callback("run_shell_command", self_termination_command_callback)                                                                                                                                                                  
                                                                                                                                                                                                                                                
register()