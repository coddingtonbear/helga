from helga import settings
from helga.extensions.base import (HelgaExtension,
                                   CommandExtension)
from helga.extensions.core import (ControlExtension,
                                   HelpExtension)
from helga.log import setup_logger


logger = setup_logger(__name__)


class ExtensionRegistry(object):

    def __init__(self, bot, load=True):
        self.bot = bot
        self.extensions = {'commands': set(), 'contexts': set()}
        self.extension_names = set()
        self.disabled_extensions = {}  # Per-channel blacklist

        if load:
            self.load()

    def _make_import_args(self, path):
        return path, {}, {}, [path.split('.')[-1]]

    def _get_possible_extensions(self, mod):
        return filter(lambda x: not x.startswith('__'), dir(mod))

    def load_module_members(self, module):
        # See if there are any HelgaExtensions
        for member in self._get_possible_extensions(module):
            cls = getattr(module, member)
            if cls == HelgaExtension:
                continue

            try:
                if issubclass(cls, HelgaExtension) and cls.NAME not in self.extension_names:
                    category = 'commands' if self._is_command(cls) else 'contexts'
                    self.extensions[category].add(cls(bot=self.bot))
                    self.extension_names.add(cls.NAME)
            except (TypeError, AttributeError):
                # Either it's not a class, or it doesn't have ``NAME``
                continue

    def load(self):
        for path in getattr(settings, 'EXTENSIONS', []):
            logger.debug('Loading extension extension %s' % path)

            try:
                module = __import__(*self._make_import_args(path))
            except ImportError:
                logger.warning('Cannot import extension %s' % path)
                continue

            self.load_module_members(module)

    def _is_command(self, ext):
        """
        Checks if an extension is a command or not
        """
        try:
            return isinstance(ext, CommandExtension)
        except TypeError:
            return False

    def _call_extension_method(self, fn, message):
        """
        Calls a function name for all extensions
        """
        # TODO: process core first

        # Nested for your pleasure
        def call_fn(fn, message, category):
            for ext in self.extensions[category]:
                if self.is_disabled(ext, message.channel):
                    logger.info('Skipping disabled extension %s on %s' % (ext.NAME, message.channel))
                    continue

                getattr(ext, fn)(message)

                if message.has_response:
                    return

        # This is kind of crappy, but commands should go first
        call_fn(fn, message, 'commands')

        # The other ones
        if not message.has_response:
            call_fn(fn, message, 'contexts')

    def preprocess(self, message):
        """
        Used to do any message preprocessing. i.e. transforming things
        """
        self._call_extension_method('preprocess', message)

    def process(self, message):
        self._call_extension_method('process', message)

    def on(self, event, *args, **kwargs):
        """
        Generalize event delegator. Sends event to all loaded extensions
        """
        # TODO: Hook events into core extensions
        for category, extensions in self.extensions.iteritems():
            for ext in extensions:
                ext.on(event, *args, **kwargs)

    def is_disabled(self, name, channel):
        """
        Returns True or False if extension is disabled on the given channel
        """
        # If it's an extension class/object
        if hasattr(name, 'NAME'):
            name = name.NAME

        return name in self.disabled_extensions.get(channel, set())

    def is_enabled(self, name, channel):
        return not self.is_disabled(name, channel)

    def disable(self, name, channel):
        """
        Disables the use of a named extension on a given channel
        """
        if channel not in self.disabled_extensions:
            self.disabled_extensions[channel] = set()

        if name not in self.extension_names:
            return False

        logger.info('Disabling %s on %s' % (name, channel))
        self.disabled_extensions[channel].add(name)

        return True

    def get_enabled(self, channel):
        """
        Returns a set of extensions enabled on this channel
        """
        return self.extension_names - self.disabled_extensions.get(channel, set())
