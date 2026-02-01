import logging

# from pyxavi import Logger

# class XLogger(Logger):
#     '''
#     Extended Logger class for PyXavi, with additional utility methods.
#     '''

#     def _log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, stacklevel=1):
#         if extra is None:
#             extra = {}
#         extra["className"] = self.__class__.__name__
#         super()._log(level, msg, args, exc_info=exc_info, extra=extra, stack_info=stack_info,
#                      stacklevel=stacklevel)
    
    

class XloggerExtrasAdapter(logging.LoggerAdapter):
    def __init__(self, logger, extra):
        super(XloggerExtrasAdapter, self).__init__(logger, extra)

    def process(self, msg, kwargs):
        if "extra" in kwargs:
            copy = dict(self.extra).copy()
            copy.update(kwargs["extra"])
            kwargs["extra"] = copy
        else:
            kwargs["extra"] = self.extra
        
        if "className" not in kwargs["extra"]:
            kwargs["extra"]["className"] = "Unknown Class"
        return msg, kwargs