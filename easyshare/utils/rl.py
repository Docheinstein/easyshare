from ctypes import c_int, CDLL, c_char_p, CFUNCTYPE
from typing import Optional, Callable

from easyshare.logging import get_logger
from easyshare.utils import c
from easyshare.utils.c import CException

log = get_logger(__name__)

_libreadline: Optional[CDLL] = None

def rl_load():
    global _libreadline

    try:
        _libreadline = c.load_library("libreadline.so")
    except:
        log.w("libreadline can't be accessed with ctypes")


def rl_get_completion_quote_character() -> int:
    """
    /* Set to any quote character readline thinks it finds before any application
    completion function is called. */
    """
    try:
        return c.get_int(_libreadline, "rl_completion_quote_character")
    except CException:
        return -1

"""
/* List of characters which can be used to quote a substring of the line.
Completion occurs on the entire substring, and within the substring
rl_completer_word_break_characters are treated as any other character,
unless they also appear within this list. */
"""

_rl_completer_quote_characters = None # keep reference for avoid GC

def rl_set_completer_quote_characters(chars: str):
    try:
        global _rl_completer_quote_characters
        _rl_completer_quote_characters = c.c_stob(chars)
        c.set_char_p(_libreadline, "rl_completer_quote_characters", _rl_completer_quote_characters)
    except:
        pass


def rl_get_completer_quote_characters() -> str:
    try:
        return c.get_char_p(_libreadline, "rl_completer_quote_characters")
    except:
        return ""



def rl_set_completion_suppress_quote(value: int):
    """
    /* If non-zero, the completion functions don't append any closing quote.
    This is set to 0 by rl_complete_internal and may be changed by an
    application-specific completion function. */
    """
    try:
        c.set_int(_libreadline, "rl_completion_suppress_quote", value)
    except:
        pass



PROTOTYPE_rl_char_is_quoted_p = CFUNCTYPE(c_int, c_char_p, c_int)

def rl_set_char_is_quoted_p(quote_detector: Callable[[str, int], int]):
    """
    /* Function to call to decide whether or not a word break character is
       quoted.  If a character is quoted, it does not break words for the
       completer. */

    int quote_detector(char * text, int index);
    """
    def rl_char_is_quoted_p_wrapper(text: bytes, index: int) -> int:
        return quote_detector(c.c_btos(text), index)

    try:
        c.set_func_ptr(_libreadline, "rl_char_is_quoted_p",
                       rl_char_is_quoted_p_wrapper, PROTOTYPE_rl_char_is_quoted_p)
    except:
        pass

# from readline.h

"""

/* **************************************************************** */
/*								    */
/*			Well Published Variables		    */
/*								    */
/* **************************************************************** */

/* The version of this incarnation of the readline library. */
extern const char *rl_library_version;		/* e.g., "4.2" */
extern int rl_readline_version;			/* e.g., 0x0402 */

/* True if this is real GNU readline. */
extern int rl_gnu_readline_p;

/* Flags word encapsulating the current readline state. */
extern unsigned long rl_readline_state;

/* Says which editing mode readline is currently using.  1 means emacs mode;
   0 means vi mode. */
extern int rl_editing_mode;

/* Insert or overwrite mode for emacs mode.  1 means insert mode; 0 means
   overwrite mode.  Reset to insert mode on each input line. */
extern int rl_insert_mode;

/* The name of the calling program.  You should initialize this to
   whatever was in argv[0].  It is used when parsing conditionals. */
extern const char *rl_readline_name;

/* The prompt readline uses.  This is set from the argument to
   readline (), and should not be assigned to directly. */
extern char *rl_prompt;

/* The prompt string that is actually displayed by rl_redisplay.  Public so
   applications can more easily supply their own redisplay functions. */
extern char *rl_display_prompt;

/* The line buffer that is in use. */
extern char *rl_line_buffer;

/* The location of point, and end. */
extern int rl_point;
extern int rl_end;

/* The mark, or saved cursor position. */
extern int rl_mark;

/* Flag to indicate that readline has finished with the current input
   line and should return it. */
extern int rl_done;

/* If set to a character value, that will be the next keystroke read. */
extern int rl_pending_input;

/* Non-zero if we called this function from _rl_dispatch().  It's present
   so functions can find out whether they were called from a key binding
   or directly from an application. */
extern int rl_dispatching;

/* Non-zero if the user typed a numeric argument before executing the
   current function. */
extern int rl_explicit_arg;

/* The current value of the numeric argument specified by the user. */
extern int rl_numeric_arg;

/* The address of the last command function Readline executed. */
extern rl_command_func_t *rl_last_func;

/* The name of the terminal to use. */
extern const char *rl_terminal_name;

/* The input and output streams. */
extern FILE *rl_instream;
extern FILE *rl_outstream;

/* If non-zero, Readline gives values of LINES and COLUMNS from the environment
   greater precedence than values fetched from the kernel when computing the
   screen dimensions. */
extern int rl_prefer_env_winsize;

/* If non-zero, then this is the address of a function to call just
   before readline_internal () prints the first prompt. */
extern rl_hook_func_t *rl_startup_hook;

/* If non-zero, this is the address of a function to call just before
   readline_internal_setup () returns and readline_internal starts
   reading input characters. */
extern rl_hook_func_t *rl_pre_input_hook;
      
/* The address of a function to call periodically while Readline is
   awaiting character input, or NULL, for no event handling. */
extern rl_hook_func_t *rl_event_hook;

/* The address of a function to call if a read is interrupted by a signal. */
extern rl_hook_func_t *rl_signal_event_hook;

/* The address of a function to call if Readline needs to know whether or not
   there is data available from the current input source. */
extern rl_hook_func_t *rl_input_available_hook;

/* The address of the function to call to fetch a character from the current
   Readline input stream */
extern rl_getc_func_t *rl_getc_function;

extern rl_voidfunc_t *rl_redisplay_function;

extern rl_vintfunc_t *rl_prep_term_function;
extern rl_voidfunc_t *rl_deprep_term_function;

/* Dispatch variables. */
extern Keymap rl_executing_keymap;
extern Keymap rl_binding_keymap;

extern int rl_executing_key;
extern char *rl_executing_keyseq;
extern int rl_key_sequence_length;

/* Display variables. */
/* If non-zero, readline will erase the entire line, including any prompt,
   if the only thing typed on an otherwise-blank line is something bound to
   rl_newline. */
extern int rl_erase_empty_line;

/* If non-zero, the application has already printed the prompt (rl_prompt)
   before calling readline, so readline should not output it the first time
   redisplay is done. */
extern int rl_already_prompted;

/* A non-zero value means to read only this many characters rather than
   up to a character bound to accept-line. */
extern int rl_num_chars_to_read;

/* The text of a currently-executing keyboard macro. */
extern char *rl_executing_macro;

/* Variables to control readline signal handling. */
/* If non-zero, readline will install its own signal handlers for
   SIGINT, SIGTERM, SIGQUIT, SIGALRM, SIGTSTP, SIGTTIN, and SIGTTOU. */
extern int rl_catch_signals;

/* If non-zero, readline will install a signal handler for SIGWINCH
   that also attempts to call any calling application's SIGWINCH signal
   handler.  Note that the terminal is not cleaned up before the
   application's signal handler is called; use rl_cleanup_after_signal()
   to do that. */
extern int rl_catch_sigwinch;

/* If non-zero, the readline SIGWINCH handler will modify LINES and
   COLUMNS in the environment. */
extern int rl_change_environment;

/* Completion variables. */
/* Pointer to the generator function for completion_matches ().
   NULL means to use rl_filename_completion_function (), the default
   filename completer. */
extern rl_compentry_func_t *rl_completion_entry_function;

/* Optional generator for menu completion.  Default is
   rl_completion_entry_function (rl_filename_completion_function). */
extern rl_compentry_func_t *rl_menu_completion_entry_function;

/* If rl_ignore_some_completions_function is non-NULL it is the address
   of a function to call after all of the possible matches have been
   generated, but before the actual completion is done to the input line.
   The function is called with one argument; a NULL terminated array
   of (char *).  If your function removes any of the elements, they
   must be free()'ed. */
extern rl_compignore_func_t *rl_ignore_some_completions_function;

/* Pointer to alternative function to create matches.
   Function is called with TEXT, START, and END.
   START and END are indices in RL_LINE_BUFFER saying what the boundaries
   of TEXT are.
   If this function exists and returns NULL then call the value of
   rl_completion_entry_function to try to match, otherwise use the
   array of strings returned. */
extern rl_completion_func_t *rl_attempted_completion_function;

/* The basic list of characters that signal a break between words for the
   completer routine.  The initial contents of this variable is what
   breaks words in the shell, i.e. "n\"\\'`@$>". */
extern const char *rl_basic_word_break_characters;

/* The list of characters that signal a break between words for
   rl_complete_internal.  The default list is the contents of
   rl_basic_word_break_characters.  */
extern /*const*/ char *rl_completer_word_break_characters;

/* Hook function to allow an application to set the completion word
   break characters before readline breaks up the line.  Allows
   position-dependent word break characters. */
extern rl_cpvfunc_t *rl_completion_word_break_hook;

/* List of characters which can be used to quote a substring of the line.
   Completion occurs on the entire substring, and within the substring   
   rl_completer_word_break_characters are treated as any other character,
   unless they also appear within this list. */
extern const char *rl_completer_quote_characters;

/* List of quote characters which cause a word break. */
extern const char *rl_basic_quote_characters;

/* List of characters that need to be quoted in filenames by the completer. */
extern const char *rl_filename_quote_characters;

/* List of characters that are word break characters, but should be left
   in TEXT when it is passed to the completion function.  The shell uses
   this to help determine what kind of completing to do. */
extern const char *rl_special_prefixes;

/* If non-zero, then this is the address of a function to call when
   completing on a directory name.  The function is called with
   the address of a string (the current directory name) as an arg.  It
   changes what is displayed when the possible completions are printed
   or inserted.  The directory completion hook should perform
   any necessary dequoting.  This function should return 1 if it modifies
   the directory name pointer passed as an argument.  If the directory
   completion hook returns 0, it should not modify the directory name
   pointer passed as an argument. */
extern rl_icppfunc_t *rl_directory_completion_hook;

/* If non-zero, this is the address of a function to call when completing
   a directory name.  This function takes the address of the directory name
   to be modified as an argument.  Unlike rl_directory_completion_hook, it
   only modifies the directory name used in opendir(2), not what is displayed
   when the possible completions are printed or inserted.  If set, it takes
   precedence over rl_directory_completion_hook.  The directory rewrite
   hook should perform any necessary dequoting.  This function has the same
   return value properties as the directory_completion_hook.

   I'm not happy with how this works yet, so it's undocumented.  I'm trying
   it in bash to see how well it goes. */
extern rl_icppfunc_t *rl_directory_rewrite_hook;

/* If non-zero, this is the address of a function for the completer to call
   before deciding which character to append to a completed name.  It should
   modify the directory name passed as an argument if appropriate, and return
   non-zero if it modifies the name.  This should not worry about dequoting
   the filename; that has already happened by the time it gets here. */
extern rl_icppfunc_t *rl_filename_stat_hook;

/* If non-zero, this is the address of a function to call when reading
   directory entries from the filesystem for completion and comparing
   them to the partial word to be completed.  The function should
   either return its first argument (if no conversion takes place) or
   newly-allocated memory.  This can, for instance, convert filenames
   between character sets for comparison against what's typed at the
   keyboard.  The returned value is what is added to the list of
   matches.  The second argument is the length of the filename to be
   converted. */
extern rl_dequote_func_t *rl_filename_rewrite_hook;

/* Backwards compatibility with previous versions of readline. */
#define rl_symbolic_link_hook rl_directory_completion_hook

/* If non-zero, then this is the address of a function to call when
   completing a word would normally display the list of possible matches.
   This function is called instead of actually doing the display.
   It takes three arguments: (char **matches, int num_matches, int max_length)
   where MATCHES is the array of strings that matched, NUM_MATCHES is the
   number of strings in that array, and MAX_LENGTH is the length of the
   longest string in that array. */
extern rl_compdisp_func_t *rl_completion_display_matches_hook;

/* Non-zero means that the results of the matches are to be treated
   as filenames.  This is ALWAYS zero on entry, and can only be changed
   within a completion entry finder function. */
extern int rl_filename_completion_desired;

/* Non-zero means that the results of the matches are to be quoted using
   double quotes (or an application-specific quoting mechanism) if the
   filename contains any characters in rl_word_break_chars.  This is
   ALWAYS non-zero on entry, and can only be changed within a completion
   entry finder function. */
extern int rl_filename_quoting_desired;

/* Set to a function to quote a filename in an application-specific fashion.
   Called with the text to quote, the type of match found (single or multiple)
   and a pointer to the quoting character to be used, which the function can
   reset if desired. */
extern rl_quote_func_t *rl_filename_quoting_function;

/* Function to call to remove quoting characters from a filename.  Called
   before completion is attempted, so the embedded quotes do not interfere
   with matching names in the file system. */
extern rl_dequote_func_t *rl_filename_dequoting_function;

/* Function to call to decide whether or not a word break character is
   quoted.  If a character is quoted, it does not break words for the
   completer. */
extern rl_linebuf_func_t *rl_char_is_quoted_p;

/* Non-zero means to suppress normal filename completion after the
   user-specified completion function has been called. */
extern int rl_attempted_completion_over;

/* Set to a character describing the type of completion being attempted by
   rl_complete_internal; available for use by application completion
   functions. */
extern int rl_completion_type;

/* Set to the last key used to invoke one of the completion functions */
extern int rl_completion_invoking_key;

/* Up to this many items will be displayed in response to a
   possible-completions call.  After that, we ask the user if she
   is sure she wants to see them all.  The default value is 100. */
extern int rl_completion_query_items;

/* Character appended to completed words when at the end of the line.  The
   default is a space.  Nothing is added if this is '\0'. */
extern int rl_completion_append_character;

/* If set to non-zero by an application completion function,
   rl_completion_append_character will not be appended. */
extern int rl_completion_suppress_append;

/* Set to any quote character readline thinks it finds before any application
   completion function is called. */
extern int rl_completion_quote_character;

/* Set to a non-zero value if readline found quoting anywhere in the word to
   be completed; set before any application completion function is called. */
extern int rl_completion_found_quote;

/* If non-zero, the completion functions don't append any closing quote.
   This is set to 0 by rl_complete_internal and may be changed by an
   application-specific completion function. */
extern int rl_completion_suppress_quote;

/* If non-zero, readline will sort the completion matches.  On by default. */
extern int rl_sort_completion_matches;

/* If non-zero, a slash will be appended to completed filenames that are
   symbolic links to directory names, subject to the value of the
   mark-directories variable (which is user-settable).  This exists so
   that application completion functions can override the user's preference
   (set via the mark-symlinked-directories variable) if appropriate.
   It's set to the value of _rl_complete_mark_symlink_dirs in
   rl_complete_internal before any application-specific completion
   function is called, so without that function doing anything, the user's
   preferences are honored. */
extern int rl_completion_mark_symlink_dirs;

/* If non-zero, then disallow duplicates in the matches. */
extern int rl_ignore_completion_duplicates;

/* If this is non-zero, completion is (temporarily) inhibited, and the
   completion character will be inserted as any other. */
extern int rl_inhibit_completion;

/* Applications can set this to non-zero to have readline's signal handlers
   installed during the entire duration of reading a complete line, as in
   readline-6.2.  This should be used with care, because it can result in
   readline receiving signals and not handling them until it's called again
   via rl_callback_read_char, thereby stealing them from the application.
   By default, signal handlers are only active while readline is active. */   
extern int rl_persistent_signal_handlers;

"""