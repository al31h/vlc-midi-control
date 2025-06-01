import argparse
import os
import sys
import rtmidi
import vlc
import time
from datetime import datetime

# =============================================================================
# Configuration
# =============================================================================
# This script allows you to read a data file and display its contents as a table.
# It also includes options to:
# - Specify the data file
# - Check the existence of a directory
# - List available MIDI ports
# - Provide an optional string to display
# - Enable verbose mode for detailed output
# - Specify a MIDI input port to receive commands
# - Handle a "live prompt" scenario with a setlist file
#
# The data file is expected to have three columns per line:
# (string, integer, time in HH:MM:SS format).
# =============================================================================

# structure of set list file
SETLIST_INDEX = 0
SETLIST_MEDIANAME = 1
SETLIST_PLAYSPEED = 2
SETLIST_STARTTIME = 3
SETLIST_ENDTIME=4

def read_setlist(file_name):
    """
    Function to read a file and load its content into a table. This function works with LivePrompter setlist, or more complete setlists
    
    Args:
    - file_name (str): Path to the file to read.
    
    Returns:
    - data_table (list): A list containing the data read, with each line being
      a sublist containing the index, string, integer, start time, and end time.
      
    Format of Input File
    - TODO : for video support, add arguments for zoom and other as needed
    """
    setlist_table = []
    try:
        with open(file_name, 'r') as file:
            for index, line in enumerate(file):
                line = line.strip()
                if not line:
                    continue  # Skip empty lines
                #if ',' in line:
                elements = line.split(',')
                #else:
                #    elements = line.split()

                if len(elements) < 2:
                    print(f"Error at line {index + 1}: Missing mandatory elements Index and Media filename ({line})")
                    continue

                # Extract the mandatory string
                media_index = int(elements[SETLIST_INDEX])-1
                media_name = elements[SETLIST_MEDIANAME]

                # Default values for the other fields
                play_speed = 100
                start_time = "00:00:00"
                end_time = "99:59:59"

                # Set optional values if they exist in the line
                if len(elements) > SETLIST_PLAYSPEED:
                    try:
                        play_speed = int(elements[SETLIST_PLAYSPEED])
                    except ValueError:
                        print(f"Error at line {index + 1}: '{elements[SETLIST_PLAYSPEED]}' is not an integer.")
                        continue

                if len(elements) > SETLIST_STARTTIME:
                    start_time = elements[SETLIST_STARTTIME]

                if len(elements) > SETLIST_ENDTIME:
                    end_time = elements[SETLIST_ENDTIME]

                # Validate times (start and end) to be in HH:MM:SS format
                def validate_time_format(time_str):
                    try:
                        parts = time_str.split(':')
                        if len(parts) != 3:
                            return False
                        hours, minutes, seconds = map(int, parts)
                        return 0 <= hours <= 99 and 0 <= minutes < 60 and 0 <= seconds < 60
                    except ValueError:
                        return False

                if not validate_time_format(start_time):
                    print(f"Error at line {index + 1}: Invalid start time format '{start_time}'")
                    continue

                if not validate_time_format(end_time):
                    print(f"Error at line {index + 1}: Invalid end time format '{end_time}'")
                    continue

                # Append the data (media_index, string, integer, start time, end time)
                setlist_table.append([media_index, media_name, play_speed, start_time, end_time])

        return setlist_table

    except FileNotFoundError:
        print(f"Setlist file not found: {file_name}")
        return []
    except Exception as e:
        print(f"Error reading the Setlist file: {e}")
        return []

def resolve_file_path(filename, default_path, default_ext): 
    resolved_setlist = []

    # check if the media filename has an extension. If not, add the defautl extension if defined, otherwise, do nothing
    if not test_filename_has_extension(filename):
        if default_ext:
            if not default_ext.startswith('.'):
                filename = filename + '.'
            filename = filename + default_ext

    # check if the media filename is absolute (has a full path)
    if not test_filename_has_fullpath(filename):
        if default_path:
            filename = os.path.join(default_path, filename)
                
    return filename

def resolve_setlist_files_path(setlist_table, default_path, default_ext): 
    resolved_setlist = []
    for media in setlist_table:
        media_index = media[0]
        media_name = media[1]
        media_playrate = media[2]
        media_start = media[3]
        media_end = media[4]
                
        # print(f"index = {media_index} - name = {media_name} - rate = {media_playrate} - start at {media_start} - end at {media_end}")
        resolved_setlist.append([media_index, resolve_file_path(media_name, default_path, default_ext), media_playrate, media_start, media_end])
    
    return resolved_setlist


def get_mediadesc_by_index(setlist_table, media_index):
    for media_desc in setlist_table:
        if media_desc[SETLIST_INDEX] == media_index:
            return media_desc
            
    return None
    
# =============================================================================
# Misc functions to check if folders and files exist
# =============================================================================
def check_directory(path):
    """
    Checks if a directory exists.
    
    Args:
    - path (str): The path of the directory to check.
    
    Returns:
    - bool: True if the directory exists, otherwise False.
    """
    return os.path.isdir(path)

def check_ext_in_path(path, ext):
    if not os.path.isdir(path):
        print(f"Error: The directory '{path}' does not exist.")
        return False

    # Vérifie les fichiers dans le dossier
    found = any(
        os.path.isfile(os.path.join(path, filename)) and filename.endswith(ext)
        for filename in os.listdir(path)
    )

    if found:
        return True
    else:
        return False

def check_file_exists(fullpath):
    if os.path.isfile(fullpath):
        return True
    else:
        return False
    
def check_file_in_path(path, filename):
    fullpath = os.path.join(path, filename)
    return check_file_exists(fullpath)

def test_filename_has_fullpath(filename):
    return os.path.isabs(filename)
    
def test_filename_has_extension(filename):
    return bool(os.path.splitext(filename)[1])
    
# =============================================================================
# To have a clean output in case of invalid command line option. The online help is displayed with a message indicating which parameter is wrong
# =============================================================================
class CustomArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print(f"Invalid command line options : {message}\n")
        self.print_help()
        sys.exit(2)

# =============================================================================
# MIDI Interface utilities
# =============================================================================
def get_inputport_table(midi_input_ports, verbose):
    
    result = []
        
    ports = midi_input_ports.get_ports()
    if not ports:
        if verbose:
            print("No available MIDI ports")
    else:
        if verbose:
            print("Available ports:")

        for port in ports:
            port_desc = port.split()
            port_id = int(port_desc[-1])
            port_name = " ".join(port_desc[:-1])
            result.append((port_name, port_id))
            if verbose:
                print(f"- {port_name}")
            
    return result
    
def get_portid_by_name(port_name, ports_table, verbose=False):
    if port_name != "":
        for port in ports_table:
            if port_name.lower() in port[0].lower():
                return port[1]
    return -1
    
def list_midi_input_ports():
    """
    Lists available MIDI input ports.
    """
    ports = midi_input_ports.get_ports()
    if not ports:
        print("No available MIDI Input ports.")
    else:
        print("Available MIDI Input ports:")
        for port in ports:
            print(f"- {port}")
        print("Use option --input <number> to specify the MIDI port to be used to receive commands (port 0 is sueed by default)")

def check_midi_input_port(input_port, verbose):
    """
    Lists available MIDI input ports.
    """
    ports = midi_input_ports.get_ports()
    if not ports:
        print("No available MIDI Input ports.")
        return False
    elif input_port < 0 or input_port >= len(ports):
        print("The specific MIDI port is not available. Please use the option --midiports to get the list of available ports.")
        return False
    else:
        if verbose:
            print(f"Using MIDI port: {ports[1]}")
        return True

# =============================================================================
# MIDI Messages utilities
# =============================================================================
# Mapping of MIDI command status bytes (upper nibble)
MIDI_COMMANDS = {
    0x80: "Note Off",
    0x90: "Note On",
    0xA0: "Polyphonic Key Pressure",
    0xB0: "Control Change",
    0xC0: "Program Change",
    0xD0: "Channel Pressure",
    0xE0: "Pitch Bend",
    0xF0: "System Message",
}

# Note names for converting MIDI note numbers to musical names
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def note_number_to_name(note_number):
    """Convert MIDI note number to note name (e.g. 60 -> C4)."""
    name = NOTE_NAMES[note_number % 12]
    octave = (note_number // 12) - 1
    return f"{name}{octave}"

def decode_midi_message(message):
    """Decode a raw MIDI message into human-readable format with parameters."""
    status = message[0]
    command = status & 0xF0
    channel = (status & 0x0F) + 1  # MIDI channels are 1-based

    command_name = MIDI_COMMANDS.get(command, f"Unknown (0x{command:X})")
    output = f"{command_name} | Channel {channel} | "

    if command in [0x80, 0x90]:  # Note Off / Note On
        note = message[1]
        velocity = message[2]
        note_name = note_number_to_name(note)
        output += f"Note: {note_name} ({note}) | Velocity: {velocity}"

    elif command == 0xA0:  # Polyphonic Key Pressure
        note = message[1]
        pressure = message[2]
        note_name = note_number_to_name(note)
        output += f"Note: {note_name} ({note}) | Pressure: {pressure}"

    elif command == 0xB0:  # Control Change
        controller = message[1]
        value = message[2]
        output += f"Controller: {controller} | Value: {value}"

    elif command == 0xC0:  # Program Change
        program = message[1]
        output += f"Program: {program}"

    elif command == 0xD0:  # Channel Pressure
        pressure = message[1]
        output += f"Pressure: {pressure}"

    elif command == 0xE0:  # Pitch Bend
        lsb = message[1]
        msb = message[2]
        value = (msb << 7) | lsb
        output += f"Pitch Bend: {value - 8192} (raw: {value})"

    elif command == 0xF0:  # System Messages
        output += f"Data: {message[1:]}"

    else:
        output += f"Raw data: {message[1:]}"

    return output

# =============================================================================
# Interface with VLC
# vlc_create_instance
# vlc_kill_all_instances
# vlc_load_media_in_instance
# vlc_play_instance
# vlc_pause_instance
# vlc_stop_instance
# =============================================================================
vlc_players = []

def vlc_create_instance(verbose = False):
    try:
        vlc_instance = vlc.Instance()
        mediaplayer = vlc_instance.MediaPlayer()
        time.sleep(0.5)
    
        vlc_players.append([mediaplayer, player])
        return len(vlc_players)-1
        
    except Exception as e:
        if verbose:
            print(f"vlc_create_instance: {e}")
        return -1

def vlc_kill_all_instances(verbose = False):
    try:
        n = 0
        for vlc_instance in vlc_players:
            print(f"Killing instance {n+1}")
            n += 1

        return True
        
    except Exception as e:
        if verbose:
            print(f"vlc_kill_all_instances: {e}")
        return False

def vlc_load_media_in_instance(player_index, media_desc, verbose = False):
    # The instance index is the value returned by vlc_create_instance
    # The media_desc is the structure made of [index, media file name, play rate, start, end]
    if player_index >= 0 and media:
        instance = vlc_players[player_index]
        mediaplayer = instance[0]
        player = instance[1]

        try:
            media = mediaplayer.media_new(media_desc[1])
            player.set_media(media)
            return True
        except Exception as e:
            if verbose:
                print(f"vlc_load_media_in_instance: {e}")
            return False
    else:
        return False

def vlc_play_instance(player_index, verbose = False):
    if player_index >= 0:
        instance = vlc_players[player_index]
        mediaplayer = instance[0]
        player = instance[1]

        try:
            player.play()
            return True
        except Exception as e:
            if verbose:
                print(f"vlc_play_instance: {e}")
            return False
    else:
        return False
            
def vlc_pause_instance(player_index, verbose = False):
    if player_index >= 0:
        instance = vlc_players[player_index]
        mediaplayer = instance[0]
        player = instance[1]

        try:
            player.pause()
            return True
        except Exception as e:
            if verbose:
                print(f"vlc_pause_instance: {e}")
            return False
    else:
        return False

def vlc_stop_instance(player_index, verbose = False):
    if player_index >= 0:
        instance = vlc_players[player_index]
        mediaplayer = instance[0]
        player = instance[1]

        try:
            player.stop()
            return True
        except Exception as e:
            if verbose:
                print(f"vlc_stop_instance: {e}")
            return False
    else:
        return False
        
        
    
# =============================================================================
# Interface with LivePrompter
# =============================================================================
def handle_live_prompter(liveprompter_path, setlist_name):
    """
    Handles the live prompt scenario where a specific setlist is required.
    
    Args:
    - liveprompter_path (str): The path to the liveprompter directory.
    - setlist_name (str): The name of the setlist file to look for.
    
    Returns:
    - bool: True if the setlist file exists, otherwise False.
    """
    setlist_path = os.path.join(liveprompter_path, 'Setlists', setlist_name)
    if not os.path.isfile(setlist_path):
        print(f"Error: The setlist file '{setlist_name}' does not exist in './Setlists'.")
        return False
    print(f"Using setlist: {setlist_name}")
    return True


# =============================================================================
# MAIN (INIT THEN LOOP UNTIL KEYBOARD INTERRUPTION)
# =============================================================================
def main():
    
    # =============================================================================
    # Argument Parsing (Command-line Options)
    # =============================================================================
    # parser = argparse.ArgumentParser(description="Read a data file and display it as a table.")
    parser = CustomArgumentParser(description="Control the VLC player with MIDI commands, to play backing tracks or videos.")
    
    # Option to use a cofniguration file
    parser.add_argument('-c', '--config', help="Filename of the configuration file")
    
    # Option to list available MIDI ports
    parser.add_argument('-ml', '--midiports', action='store_true', help="List available MIDI ports")
    
    # Option to specify MIDI input port number
    parser.add_argument('-mi', '--midi-input', help="MIDI input port name to use for receiving commands")
    
    # Option to specify MIDI input port number
    parser.add_argument('-mc', '--midi-channel', help="MIDI channel on which the commands are received")
    
    # Option to specify the set file
    parser.add_argument('-s', '--setlist', required=False, help="Name of the file containing the Set List. The file should have the following structure:\n"
                                                           "1. Filename of the media to play\n"
                                                           "2. (optional) Play Rate in %% (default is 100).\n"
                                                           "3. (optional) Start time in HH:MM:SS format (default is '00:00:00').\n"
                                                           "4. (optional) End time in HH:MM:SS format (default is '99:59:59').\n"
                                                           "Example: 'Alice,23,12:30:00,13:00:00' or 'Bob,42,14:00:00' or 'Charlie,,15:00:00,99:59:59'")
    
    # Option for live prompter mode
    parser.add_argument('-lp', '--liveprompter', required=False, help="Path to the liveprompter directory")
    
    # Option to check a directory
    parser.add_argument('-p', '--path', help="Default path of media files to play (if not specified in the playlist)")
    
    # Option to provide an optional string (extension)
    parser.add_argument('-e', '--extension', help="Default filename extension for media files to play")

    # Option to ignore missing media error (by default, the program checks if media file exist before starting to wait MIDI commands)
    parser.add_argument('-um', '--ignore-missing-media', action='store_true', help="Unsafe mode - Ignore missing media error - Can lead to uncontroled behavior. DO NOT USE IN LIVE")

    # Option to specify the default media file if a media file could not be found 
    parser.add_argument('-dm', '--default-missing-media', help="Filename of the media file played if a media file is missing.")

    # Option for verbose output
    parser.add_argument('-v', '--verbose', action='store_true', help="Enable verbose output")
    
    # Option for more help (description of files and folder structures)
    parser.add_argument('-mh', '--morehelp', action='store_true', help="Provide more help about files and folders structures")
    
    
    # Parse command-line arguments
    args = parser.parse_args()

    # =============================================================================
    # Handle More Help Mode: display help and exit
    # =============================================================================
    if args.morehelp:
        help_setlist = '''
        More Help of SetList file
        1. Filename of the media to play
        2. (optional) Play Rate in %% (default is 100)
        3. (optional) Start time in HH:MM:SS format (default is '00:00:00')
        4. (optional) End time in HH:MM:SS format (default is '99:59:59')
        
        Fields are separated by a comma. 
        If the media filename is full, with path and extension, it will be used as is.
        If the media filename does not include the full path, the path specified by option --path will be used to find the file
        If the media filename does not include the extension (e.g. .mp3), the default extension specified bu topion --ext will be added to the filename
        
        
        '''
        print(help_setlist)
        exit(0)
        
    # =============================================================================
    # Handle Verbose Mode
    # =============================================================================
    verbose = args.verbose  # If --verbose is specified, set verbose to True
    if verbose:
        print("Verbose mode enabled.")

    # =============================================================================
    # Unsafe mode options
    # um (ignore-missing-media): ignore missing media error
    # =============================================================================
    unsafeIgnoreMissingMedia = args.ignore_missing_media  # If --verbose is specified, set verbose to True
    if unsafeIgnoreMissingMedia:
        print("WARINING: UNSAFE MODE FOR LIVE - Missing files error is ignored.")

    # =============================================================================
    # Default media played in case of errors
    # dm (default-missing-media)
    # =============================================================================
    defaultMediaFile = ""
    if args.default_missing_media:
        defaultMediaFile = resolve_file_path(args.default_missing_media, args.path, args.extension)
        # check 

    # =============================================================================
    # List MIDI ports if the option is specified
    # Option treated first, to exist the program after displaying the list of available ports
    # =============================================================================
    midi_input_ports = rtmidi.MidiIn()
    inputports_table = get_inputport_table(midi_input_ports, verbose) # used later to open the port
    
    if args.midiports:
        if inputports_table:
            print(inputports_table)
        else:
            print("No MIDI Input Ports found.")
        #list_midi_input_ports()
        exit(0)

    # =============================================================================
    # Check if the specified files and folders exist
    # =============================================================================
    if args.config:
        if not check_file_exists(args.config):
            print(f"Error: Configuration file {args.config} could not be found. Program stopped.")
            exit(1)

    if args.setlist:
        if not check_file_exists(args.setlist):
            print(f"Error: SetList file {args.setlist} could not be found. Program stopped.")
            exit(1)
    
    if args.path:
        if not check_directory(args.path):
            print(f"Error: Path {args.path} could not be found. Program stopped.")
            exit(1)  # Exit if the directory doesn't exist

    if args.path and args.extension:
        if not check_ext_in_path(args.path, args.extension):
            print(f"Error: No file with extension {args.extension} could be found in specified path {args.path}.")
            exit(1)


    # =============================================================================
    # Display the provided extension (if any)
    # =============================================================================
    if args.extension and verbose:
        print(f"Extension provided: {args.extension}")



    # =============================================================================
    # Handle Live Prompter Mode
    # =============================================================================
    if args.liveprompter:
        # Ensure the option --liveprompter is mutually exclusive with --setlist
        if args.setlist:
            print("Error: '--liveprompter' and '--setlist' are mutually exclusive.")
            exit(1)
        
        # Verify the existence of the liveprompter directory
        if not check_directory(args.liveprompter):
            exit(1)

        # Ensure that the --setlist option is provided when --liveprompter is used
        if not args.setlist:
            print("Error: '--setlist' is required when using '--liveprompter'.")
            exit(1)

        # Check if the specified setlist file exists in the './Setlists' directory
        if not handle_live_prompter(args.liveprompter, args.setlist):
            exit(1)

    # =============================================================================
    # Build the playlist, based on the set list provided by option --setlist
    # =============================================================================
    raw_setlist = []
    if args.setlist:
        # Calculate the file's directory path and the file name
        setlist_directory_path = os.path.abspath(os.path.dirname(args.setlist))  # The directory containing the file
        setlist_filename = os.path.basename(args.setlist)  # The file's name (with extension)

        raw_setlist = read_setlist(args.setlist)


        
    # =============================================================================
    # Finalize the setlist by resolving missing path and file extension
    # =============================================================================
    if not raw_setlist:
        print(f"Error: Empty setlist. Program stopped.")
        exit(2)

    resolved_setlist = resolve_setlist_files_path(raw_setlist, args.path, args.extension)

    if not resolved_setlist:
        print(f"Error: Empty setlist. Program stopped.")
        exit(2)
        
    # check if all media file exist
    disperror = False
    if not unsafeIgnoreMissingMedia:
        for media in resolved_setlist:
            filename = media[1]
            fileok = check_file_exists(filename)
            if not fileok:
                disperror = True
            if disperror:
                print(f"Error: Media {filename} not found.")
        if disperror:
            print(f"Error: At least 1 media file could not be found. Program stopped.")
            print(f"Check the setlist and path specified in the configuration file.")
            exit(2)
        
    # Display the results in verbose mode if enabled
    if verbose:
        print("Displaying setlist content in verbose mode:")
        for row in resolved_setlist:
            print(row)


    # =============================================================================
    # Load the Playlist in VLC
    # vlc_create_instance
    # vlc_kill_all_instances
    # vlc_load_media_in_instance
    # vlc_play_instance
    # vlc_pause_instance
    # vlc_stop_instance
    # =============================================================================
    # creating a vlc instance
    #vlc_player_main = vlc_create_instance(verbose)
    #if vlc_player_main < 0:
    #    print(f"Error: Unable to launch the main VLC instance. Program Stopped.")
    #    exit(2)
        
    # launch the second VLC instance for the click

    # =============================================================================
    # Handle MIDI Input Port
    # =============================================================================
    midi_input_portname = ""  # TODO : get_from_configfile
    if args.midi_input:
        midi_input_portname = args.midi_input  # Store the MIDI input port number if provided

    if args.midi_channel:
        midi_channel = int(args.midi_channel)
    else:
        print(f"WARNING - Defaulting to use the MIDI channel 0")
        midi_channel = 0

    # END OF INIT - REAL-TIME PART
    

    # =============================================================================
    # Open VLC instances
    # =============================================================================
    vlc_instance_main = vlc.Instance()
    vlc_player_click = None
    vlc_player_video = None
    
    time.sleep(0.5)
    player_main = vlc_instance_main.media_player_new()







    # =============================================================================
    # Open the MIDI Input Port
    # =============================================================================
    portid = get_portid_by_name(midi_input_portname, inputports_table, verbose)
    if portid == -1:
        print(f"MIDI port {midi_input_portname} not found. Program stopped.")
        exit(1)
        
    if verbose:
        print(f"MIDI port selected: {portid}")
        
    # open the MIDI Input Port
    try:
        selected_midi_input_port = midi_input_ports.open_port(portid)
    except Exception as e:
        if verbose:
            print(f"Unable to open the selected MIDI Input Port {midi_input_portname}: {e}. Program stopped.")
        exit(2)
    
    # load a media for tests
    
    PLAYPAUSE_MODE_PLAYONLY = 0   # distinct command for pause
    PLAYPAUSE_MODE_TOGGLE = 1     # case of play/pause button in LivePrompter
    cmd_playpause_mode = PLAYPAUSE_MODE_TOGGLE
    
    PLAYPAUSE_STATUS_PAUSE = 0
    PLAYPAUSE_STATUS_PLAY = 1
    cmd_playpause_status = PLAYPAUSE_STATUS_PAUSE
    
    try:
        while True:
            while selected_midi_input_port.is_port_open():
                inmsg = selected_midi_input_port.get_message()
                if inmsg:
                    (msg, dt) = inmsg
                    command = msg[0] & 0xF0
                    channel = (msg[0] & 0x0F) + 1

                    if verbose:
                        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # e.g. 14:52:03.123
                        #print(f"[{timestamp}] MIDI Input: {decode_midi_message(msg)}")
                        #print(f"Received MIDI message {msg} - Command {hex(command)} on channel {channel}")
                        
                    if channel == midi_channel:
                        
                        if command == 0xC0:   # Program Change = change media to be played
                            player_main.stop()
                            cmd_playpause_status = PLAYPAUSE_STATUS_PAUSE

                            playlist_index = msg[1]
                            
                            if playlist_index >= 0 and playlist_index < len(resolved_setlist):
                                media_desc = get_mediadesc_by_index(resolved_setlist, playlist_index)
                                print(f"media_desc = {media_desc}")
                                if media_desc and check_file_exists(media_desc[1]):
                                    if verbose:
                                        print(f"Info: loading {media_desc[1]}")
                                    media_main = vlc_instance_main.media_new(media_desc[1])
                                    player_main.set_media(media_main)
                                else:
                                    if check_file_exists(defaultMediaFile):
                                        media_main = vlc_instance_main.media_new(defaultMediaFile)
                                        player_main.set_media(media_main)   
                                        player_main.play()
                                        time.sleep(5)
                                        player_main.stop()
                                        cmd_playpause_status = PLAYPAUSE_STATUS_PAUSE
                                        
                                
                            else:
                                print(f"Error: received index {playlist_index} out of range vs the specified set list. Playing nothing.")
                                
                            
                            # by default, the player is not started, waiting for an explicit PLAY commmand
                            player_main.stop()
                            cmd_playpause_status = PLAYPAUSE_STATUS_PAUSE
                            
                        elif command == 0xB0: # Control Change = Play / Pause / Stop
                            transport_cmd = msg[1]
                            # Play, or play/pause buttton - handle a toggle to be synchronized with LivePromper
                            if transport_cmd == 2:
                                if cmd_playpause_mode == PLAYPAUSE_MODE_TOGGLE:
                                    if cmd_playpause_status == PLAYPAUSE_STATUS_PAUSE:
                                        player_main.play()
                                        cmd_playpause_status = PLAYPAUSE_STATUS_PLAY
                                    else:
                                        player_main.pause()
                                        cmd_playpause_status = PLAYPAUSE_STATUS_PAUSE
                                else:
                                    player_main.play()
                                    cmd_playpause_status = PLAYPAUSE_STATUS_PLAY
                                    
                            # Pause button (does not exist in LivePrompter)
                            elif transport_cmd == 3: 
                                player_main.pause()
                                cmd_playpause_status = PLAYPAUSE_STATUS_PAUSE
                                
                            # Reset button stop and be ready to play again from the beginning
                            elif transport_cmd == 9:
                                player_main.stop()
                                cmd_playpause_status = PLAYPAUSE_STATUS_PAUSE

                            # Button UP in LivePrompter
                            elif  transport_cmd == 4:
                                print(f"Received transport command UP - Ignored.")
                        
                            # Button DOWN in LivePrompter
                            elif  transport_cmd == 5:
                                print(f"Received transport command DOWN - Ignored.")
                                
                    #else:
                        #print(f"Ignoring MIDI command received on channel {channel} - waiting on channel {midi_channel}")
            time.sleep(0.010)
            
    except KeyboardInterrupt:
        player_main.stop()
        


# =============================================================================
# __MAIN__ ENTRY POINT
# =============================================================================


if __name__ == "__main__":
    
    main()

