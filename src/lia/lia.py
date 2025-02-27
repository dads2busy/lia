# src/lia/lia.py
import asyncio
import json
import os
import shlex
import pprint
import inspect
from prompt_toolkit import PromptSession
from lia.analysis_context import AnalysisContext
from typing import Union
from dataclasses import dataclass
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai import capture_run_messages, UnexpectedModelBehavior
from lia.agent import load_agent, list_agents, AgentDeps

class Lia:
    prompt = "(Lia) > "
    message_history = []

    def __init__(self, context: AnalysisContext, file: Union[str, None], options):
        self.context = context
        self.file = file
        self.options = options

        self.default_model = OpenAIModel(
            model_name=self.options.model_name,
            base_url=self.options.llm_api_url,
            api_key=self.options.llm_api_key
        )
        if options.agent is not None:
            self.default_agent = load_agent(options.agent, model=self.default_model)
        else:
            self.default_agent = load_agent('context_manager_agent', model=self.default_model)
        if self.default_agent.name is not None and options.agent is not None:
            self.prompt = f"({self.default_agent.name}) >"
        if options.debug:
            pprint.pprint(self.default_agent, indent=2)

    async def run_cli(self):
        session = PromptSession(self.prompt)
        print("Starting interactive chat with Lia.\nType '/help' for commands or '/exit' to quit.\n")
        while True:
            try:
                # Use prompt_toolkit’s async prompt.
                line = await session.prompt_async(self.prompt)
            except (EOFError, KeyboardInterrupt):
                # Treat Ctrl-D (or Ctrl-C) as EOF.
                line = "EOF"
            line = line.strip()
            if not line:
                continue
            if line == "EOF":
                command_line = "EOF"
            elif line.startswith('/'):
                command_line = line[1:]
            else:
                # Prepend the "send" command if not explicitly a command.
                command_line = "send " + line
            should_exit = await self.handle_command(command_line)
            if should_exit:
                break

    async def handle_command(self, line: str) -> bool:
        parts = line.split(" ", 1)
        command = parts[0]
        arg = parts[1] if len(parts) > 1 else ""
        method_name = f"do_{command}"
        method = getattr(self, method_name, None)
        if method is None:
            print(f"Unknown command: {command}")
            return False
        if inspect.iscoroutinefunction(method):
            return await method(arg)
        else:
            return method(arg)

    def do_EOF(self, inp):
        """Exit the chat."""
        print("Bye")
        return True

    def do_exit(self, inp):
        """Exit the chat."""
        return self.do_EOF(inp)

    def do_objective(self, inp):
        """Set the objective for the current analysis context."""
        self.context.objective = inp
        return False

    def do_addQuestion(self, inp):
        """
        Adds a question to the analysis context.
        Usage: /addQuestion Who killed Virginia Wolff?
        """
        args = list(shlex.shlex(inp, posix=True))
        self.context.key_questions.append(' '.join(args))
        return False

    def do_updateQuestion(self, inp):
        """
        Update a question in the analysis context.
        Usage: /updateQuestion 2 "where is my mind?"
        """
        args = list(shlex.shlex(inp, posix=True))
        if len(args) < 2:
            print("Please provide a position and a question to update.")
            print("/updateQuestion 2 What is the new question?")
            return False
        position = int(args[0])
        newq = ' '.join(args[1:])
        self.context.key_questions[position] = newq
        return False

    def do_clear(self, inp):
        """Clears the chat history (does not change the analysis context)."""
        self.message_history = []
        return False

    def do_deleteQuestion(self, inp):
        """
        Delete a question from the analysis context.
        Usage: /deleteQuestion 2
        """
        try:
            self.context.key_questions.pop(int(inp))
        except Exception as e:
            print("Error deleting question:", e)
        return False

    def do_addConstraint(self, inp):
        """
        Adds a constraint to the analysis context.
        Usage: /addConstraint [constraint text]
        """
        args = list(shlex.shlex(inp, posix=True))
        self.context.constraints.append(' '.join(args))
        return False

    def do_updateConstraint(self, inp):
        """
        Update a constraint in the analysis context.
        Usage: /updateConstraint 2 "new constraint"
        """
        args = list(shlex.shlex(inp, posix=True))
        if len(args) < 2:
            print("Please provide a position and a constraint to update.")
            print("/updateConstraint 2 What is the new constraint?")
            return False
        position = int(args[0])
        newq = ' '.join(args[1:])
        self.context.constraints[position] = newq
        return False

    def do_deleteConstraint(self, inp):
        """
        Delete a constraint from the analysis context.
        Usage: /deleteConstraint 2
        """
        try:
            self.context.constraints.pop(int(inp))
        except Exception as e:
            print("Error deleting constraint:", e)
        return False

    def do_context(self, inp=''):
        """Display the current analysis context."""
        parts = inp.split()
        if parts:
            for key in parts:
                print(f"{getattr(self.context, key, f'Analysis Context {key} not found')}")
        else:
            print(self.context)
        return False

    def do_save(self, inp=''):
        """Save the current analysis context to a JSON file."""
        jsondata = json.dumps(self.context.dict(), indent=4)
        if self.file is not None:
            with open(self.file, 'w') as f:
                f.write(jsondata)
            print(f"Context saved to {self.file}")
        elif inp:
            with open(inp, 'w') as f:
                f.write(jsondata)
            print(f"Context saved to {inp}")
        elif getattr(self.context, 'name', ''):
            filename = f"{self.context.name}.json"
            if os.path.isfile(filename):
                print(f"File {filename} already exists. Please specify a different name.")
            else:
                with open(filename, 'w') as f:
                    f.write(jsondata)
                print(f"Context saved to {filename}")
        else:
            print("No file specified to save context.")
        return False

    def do_help(self, command):
        if not command:
            print("Commands:")
            for attr in dir(self):
                if attr.startswith("do_") and attr != "do_EOF":
                    print(f"\t{attr[3:]}")
            print("Prefix a command with '/' (for example, '/help').")
        else:
            print("No additional help available for this command.")
        return False

    def do_listAgents(self, param):
        """List the individual agents in the system."""
        agents = list_agents()
        print("Agents:")
        for agent in agents:
            print(f"  {agent}")
        return False

    async def do_send(self, user_input):
        """Send a message to the context manager agent."""
        def run_sync():
            # Create and set an event loop for this thread.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                with capture_run_messages() as messages:
                    return self.default_agent.run_sync(
                        user_input,
                        message_history=self.message_history,
                        deps=AgentDeps(analysis_context=self.context),
                        model_settings={'temperature': 0.9}
                    )
            finally:
                loop.close()

        try:
            response = await asyncio.to_thread(run_sync)
            newmsgs = response.new_messages()
            if self.options.debug:
                pprint.pprint(newmsgs, indent=2)
            self.message_history += newmsgs
            pprint.pp(response.data, indent=4)
        except UnexpectedModelBehavior as e:
            print("An error occurred:", e)
        return False
