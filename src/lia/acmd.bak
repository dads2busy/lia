import asyncio
import sys

class ACmd:
    """
    A simple asynchronous command interpreter that mimics the API of Python's cmd module.
    
    Subclass ACmd and define methods named do_<command> to implement commands.
    Command methods can be either synchronous or async coroutines.
    """
    prompt = "(async)> "
    intro = None
    stdout = sys.stdout

    async def cmdloop(self, intro=None):
        if intro is not None:
            self.intro = intro
        if self.intro:
            self.stdout.write(str(self.intro) + "\n")

        stop = False
        while not stop:
            try:
                line = await self.async_input(self.prompt)
            except EOFError:
                line = "EOF"
            line = await self.precmd(line)
            stop = await self.onecmd(line)
            stop = await self.postcmd(stop, line)
    
        # Cancel the background task on exit.
        return stop

    async def async_input(self, prompt):
        """An asynchronous wrapper for the built-in input() using run_in_executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, input, prompt)

    async def precmd(self, line):
        """Hook method executed just before the command line is interpreted."""
        return line

    async def postcmd(self, stop, line):
        """Hook method executed just after a command dispatch is finished."""
        return stop

    def parseline(self, line):
        """
        Parse the line into a command name and a string argument.
        Returns a tuple: (command, argument, line)
        """
        line = line.strip()
        if not line:
            return None, None, line
        if ' ' in line:
            cmd, arg = line.split(' ', 1)
        else:
            cmd, arg = line, ''
        return cmd, arg, line

    def emptyline(self):
        """
        Called when an empty line is entered.
        By default, do nothing.
        """
        return False

    async def onecmd(self, line):
        """
        Interpret the argument as though it had been typed at the command prompt.
        Returns True if the command loop should exit.
        """
        line = line.strip()
        if not line:
            return self.emptyline()
        cmd, arg, _ = self.parseline(line)
        if cmd is None:
            return self.emptyline()
        # Look up the command method, e.g. "do_help" for "help"
        func = getattr(self, 'do_' + cmd, None)
        if func is None:
            self.stdout.write("Unknown command: {}\n".format(cmd))
            return False
        # Call the command method; if it's a coroutine, await its result.
        result = func(arg)
        if asyncio.iscoroutine(result):
            result = await result
        return result

