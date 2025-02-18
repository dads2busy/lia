# src/lia/cmd_app.py
import cmd
from lia.analysis_context import AnalysisContext
from typing import Union
from dataclasses import dataclass
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai import capture_run_messages,UnexpectedModelBehavior
import json
import os
import shlex
from lia.agent import load_agent,list_agents,AgentDeps
from lia.agent.context_manager_agent import getAgent as getContextManagerAgent

import pprint

class Lia(cmd.Cmd):
    """
    intro = 'Welcome to Lia interactive shell. Type help or ? to list commands.\n'
    prompt = '(Lia) '
    """
    # identchars="do_"
    message_history=[]
    prompt = 'Lia > '
    def __init__(self,context:AnalysisContext,file:Union[str|None],options):
        super().__init__()
        self.context = context
        self.file = file
        self.options = options
        # self.model_name = "llama3-groq-tool-use"
        self.model_name = "djm-tools-8b2"
        self.base_url = "http://localhost:11434/v1"
        self.api_key = "none"
        self.model = OpenAIModel(model_name=self.model_name,base_url=self.base_url,api_key=self.api_key)

        # self.model_name = "gpt-4o"
        # self.api_key = "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"
        # self.model = OpenAIModel(model_name=self.model_name,api_key=self.api_key)

        # self.context_manager_agent = getContextManagerAgent(model=self.model)
        self.context_manager_agent = getContextManagerAgent(model=self.model)
        # if options.debug:
        #     pprint.pp(self.context_manager_agent,indent=2)
            
    def precmd(self, line):
        if line.startswith('/'):
            return line[1:]
        elif line=="help":
            return line
        elif line=="EOF":
            return line
        else:
            return f"send {line}"
    
    def do_EOF(self, inp):
        '''
            Exits the chat.
        '''
        print("Bye")
        return True    

    def do_objective(self,inp):
        """Set the objective for the current analysis context"""
        self.context.objective=inp
        return ''
    
    def do_addQuestion(self,inp):
        """
            Adds a question to the analysis context
            Usage: /addQuestion Who killed Virginia Wolff?
        """
        args = list(shlex.shlex(inp,posix=True))
        q = ' '.join(args)
        self.context.key_questions.append(' '.join(args))
        return ''
    
    def do_updateQuestion(self,inp):
        """
            Update question in the analysis context
            Usage: /updateQuestion 2 "where is my mind?"
        """
        args = list(shlex.shlex(inp,posix=True))

        if len(args)<2:
            print("Please provide a position and a question to update.")
            print("/updateQuery 2 What is the new question?")
            return ''
        position = int(args[0])
        newq = ' '.join(args[1:])
        self.context.key_questions[position] = newq
        return ''
    
    def do_clear(self,inp):
        """Clears the chat history.  Does not change the analysis context object."""
        self.message_history=[]
        
    def do_deleteQuestion(self,inp):
        """
            Delete a question from the analysis context
            Usage: /deleteQuestion 2
        """
        
        self.context.key_questions.pop(int(inp))
        return ''

    def do_addConstraint(self,inp):
        """
            Adds a constraint to the analysis context
            Usage: /addConstraint Who killed Virginia Wolff?
        """
        args = list(shlex.shlex(inp,posix=True))
        q = ' '.join(args)
        self.context.constraints.append(' '.join(args))
        return ''
    
    def do_updateConstraint(self,inp):
        """
            Update constraint in the analysis context
            Usage: /updateConstraint 2 "where is my mind?"
        """
        args = list(shlex.shlex(inp,posix=True))

        if len(args)<2:
            print("Please provide a position and a constraint to update.")
            print("/updateConstraint 2 What is the new question?")
            return ''
        position = int(args[0])
        newq = ' '.join(args[1:])
        self.context.constraints[position] = newq
        return ''
    
    def do_deleteConstraint(self,inp):
        """
            Delete a constraint from the analysis context
            Usage: /deleteConstraint 2
        """
        
        self.context.constraints.pop(int(inp))
        return ''
    
    def do_context(self,inp=''):
        """Display the current analysis context"""
        parts = inp.split()
        if len(parts)>0:
            for key in parts:
                print(f"{getattr(self.context,key,f'Analysis Context {key} not found')}")
        else:
            print(f"{self.context}")
        return ''
    
    def do_save(self,inp=''):
        """Save the current analysis context to a JSON file"""
        jsondata = json.dumps(self.context.dict(),indent=4)
        if self.file is not None:
            with open(self.file,'w') as f:
                f.write(jsondata)
            print(f"Context saved to {self.file}")
        elif inp != '':
            with open(inp,'w') as f:
                f.write(jsondata)
            print(f"Context saved to {inp}")
        elif self.context.name != '':
            filename = f"{self.context.name}.json"
            if os.path.isfile(filename):
                print(f"File {filename} already exists. Please specify a different name.")
            else:
                with open(filename,'w') as f:
                    f.write(jsondata)
                print(f"Context saved to {filename}")
        else:
            print("No file specified to save context.")
        return ''
    
    def do_send(self, user_input):
        """Send a message to the context manager agent"""     
        with capture_run_messages() as messages: 
            try:
                response = self.context_manager_agent.run_sync(user_input,message_history=self.message_history,deps=AgentDeps(analysis_context=self.context),model_settings={'temperature': .9})    
                newmsgs = response.new_messages()
                if self.options.debug:
                    print("***************\nNew Messages:")
                    pprint.pp(newmsgs,indent=2)
                    print("***************\n")
                self.message_history += newmsgs
                print(response.data)
                
            except UnexpectedModelBehavior as e:
                print('An error occurred:', e)
                print('cause:', repr(e.__cause__))
                pprint.pp(newmsgs,indent=2)

    def do_help(self,command):
        if command == '':
            print("Commands:")
            for name in dir(self):
                if name.startswith("do_") and name!="do_EOF":
                    print(f"\t{name.replace("do_","")}")
            print("To execute a command proceed it with a '/'.  For example '/help'")
        else:
            cmd.Cmd.do_help(self,command)     
    def emptyline(self):
        self.prompt
   
