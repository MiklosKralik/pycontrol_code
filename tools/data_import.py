# Python classes for importing pyControl data files and representing pyControl 
# sessions and experiments.  Dependencies: Python 3.5+, Numpy.

import os
import pickle
import pandas as pd
import numpy as np
from datetime import datetime, date
from collections import namedtuple

Event = namedtuple('Event', ['time','name'])

#----------------------------------------------------------------------------------
# Session class
#----------------------------------------------------------------------------------

class Session():
    '''Import data from a pyControl file and represent it as an object with attributes:
      - file_name
      - experiment_name
      - task_name
      - subject_ID
          If argument int_subject_IDs is True, suject_ID is stored as an integer,
          otherwise subject_ID is stored as a string.
      - datetime
          The date and time that the session started stored as a datetime object.
      - datetime_string
          The date and time that the session started stored as a string of format 'YYYY-MM-DD HH:MM:SS'
      - events
          A list of all framework events and state entries in the order they occured. 
          Each entry is a namedtuple with fields 'time' & 'name', such that you can get the 
          name and time of event/state entry x with x.name and x.time respectively.
      - times
          A dictionary with keys that are the names of the framework events and states and 
          corresponding values which are Numpy arrays of all the times (in milliseconds since the
           start of the framework run) at which each event/state entry occured.
      - print_lines
          A list of all the lines output by print statements during the framework run, each line starts 
          with the time in milliseconds at which it was printed.
    '''

    def __init__(self, file_path, int_subject_IDs=True):

        # Load lines from file.

        with open(file_path, 'r') as f:
            print('Importing data file: '+os.path.split(file_path)[1])
            all_lines = [line.strip() for line in f.readlines() if line.strip()]

        # Extract and store session information.

        self.file_name = os.path.split(file_path)[1]

        info_lines = [line[2:] for line in all_lines if line[0]=='I']

        self.experiment_name = next(line for line in info_lines if 'Experiment name' in line).split(' : ')[1]
        self.task_name       = next(line for line in info_lines if 'Task name'       in line).split(' : ')[1]
        subject_ID_string    = next(line for line in info_lines if 'Subject ID'      in line).split(' : ')[1]
        datetime_string      = next(line for line in info_lines if 'Start date'      in line).split(' : ')[1]

        if int_subject_IDs: # Convert subject ID string to integer.
            self.subject_ID = int(''.join([i for i in subject_ID_string if i.isdigit()]))
        else:
            self.subject_ID = subject_ID_string

        self.datetime = datetime.strptime(datetime_string, '%Y/%m/%d %H:%M:%S')
        self.datetime_string = self.datetime.strftime('%Y-%m-%d %H:%M:%S')

        # Extract and store session data.

        state_IDs = eval(next(line for line in all_lines if line[0]=='S')[2:])
        event_IDs = eval(next(line for line in all_lines if line[0]=='E')[2:])

        ID2name = {v: k for k, v in {**state_IDs, **event_IDs}.items()}

        data_lines = [line[2:].split(' ') for line in all_lines if line[0]=='D']

        self.events = [Event(int(dl[0]), ID2name[int(dl[1])]) for dl in data_lines]

        self.times = {event_name: np.array([ev.time for ev in self.events if ev.name == event_name])  
                      for event_name in ID2name.values()}

        self.print_lines = [line[2:] for line in all_lines if line[0]=='P']

#----------------------------------------------------------------------------------
# Experiment class
#----------------------------------------------------------------------------------

class Experiment():
    def __init__(self, folder_path, int_subject_IDs=True):
        '''
        Import all sessions from specified folder to create experiment object.  Only sessions in the 
        specified folder (not in subfolders) will be imported.
        Arguments:
        folder_path: Path of data folder.
        int_subject_IDs:  If True subject IDs are converted to integers, e.g. m012 is converted to 12.
        '''

        self.folder_name = os.path.split(folder_path)[1]
        self.path = folder_path

        # Import sessions.

        self.sessions = []
        try: # Load sessions from saved sessions.pkl file.
            with open(os.path.join(self.path, 'sessions.pkl'),'rb') as sessions_file:
                self.sessions = pickle.load(sessions_file)
            print('Saved sessions loaded from: sessions.pkl')
        except IOError:
            pass

        old_files = [session.file_name for session in self.sessions]
        files = os.listdir(self.path)
        new_files = [f for f in files if f[-4:] == '.txt' and f not in old_files]

        if len(new_files) > 0:
            print('Loading new data files..')
            for file_name in new_files:
                try:
                    self.sessions.append(Session(os.path.join(self.path, file_name), int_subject_IDs))
                except Exception as error_message:
                    print('Unable to import file: ' + file_name)
                    print(error_message)

        # Assign session numbers.

        self.subject_IDs = list(set([s.subject_ID for s in self.sessions]))
        self.n_subjects = len(self.subject_IDs)

        self.sessions.sort(key = lambda s:s.datetime_string + str(s.subject_ID))
        
        self.sessions_per_subject = {}
        for subject_ID in self.subject_IDs:
            subject_sessions = self.get_sessions(subject_ID)
            for i, session in enumerate(subject_sessions):
                session.number = i+1
            self.sessions_per_subject[subject_ID] = subject_sessions[-1].number

    def save(self):
        '''Save all sessions as .pkl file. Speeds up subsequent instantiation of 
        experiment as sessions do not need to be reimported from data files.''' 
        with open(os.path.join(self.path, 'sessions.pkl'),'wb') as sessions_file:
            pickle.dump(self.sessions, sessions_file)
        
    def get_sessions(self, subject_IDs='all', when='all'):
        '''Return list of sessions which match specified subject ID and time.  
        Arguments:
        subject_ID: Set to 'all' to select sessions from all subjects or provide a list of subject IDs.
        when      : Determines session number or dates to select, see example usage below:
                    when = 'all'      # All sessions
                    when = 1          # Sessions numbered 1
                    when = [3,5,8]    # Session numbered 3,5 & 8
                    when = [...,10]   # Sessions numbered <= 10
                    when = [5,...]    # Sessions numbered >= 5
                    when = [5,...,10] # Sessions numbered 5 <= n <= 10
                    when = '2017-07-07' # Select sessions from date '2017-07-07'
                    when = ['2017-07-07','2017-07-08'] # Select specified list of dates
                    when = [...,'2017-07-07'] # Select session with date <= '2017-07-07'
                    when = ['2017-07-01',...,'2017-07-07'] # Select session with '2017-07-01' <= date <= '2017-07-07'.
        '''
        if subject_IDs == 'all':
            subject_IDs = self.subject_IDs
        if not isinstance(subject_IDs, list):
            subject_IDs = [subject_IDs]

        if when == 'all': # Select all sessions.
            when_func = lambda session: True

        else:
            if type(when) is not list:
                when = [when]

            if ... in when: # Select a range..

                if len(when) == 3:  # Start and end points defined.
                    assert type(when[0]) == type(when[2]), 'Start and end of time range must be same type.'
                    if type(when[0]) == int: # .. range of session numbers.
                        when_func = lambda session: when[0] <= session.number <= when[2]
                    else: # .. range of dates.
                        when_func = lambda session: _toDate(when[0]) <= session.datetime.date() <= _toDate(when[2])
                
                elif when.index(...) == 0: # End point only defined.
                    if type(when[1]) == int: # .. range of session numbers.
                        when_func = lambda session: session.number <= when[1]
                    else: # .. range of dates.
                        when_func = lambda session: session.datetime.date() <= _toDate(when[1])

                else: # Start point only defined.
                    if type(when[0]) == int: # .. range of session numbers.
                        when_func = lambda session: when[0] <= session.number
                    else: # .. range of dates.
                        when_func = lambda session: _toDate(when[0]) <= session.datetime.date()
                
            else: # Select specified..
                assert all([type(when[0]) == type(w) for w in when]), "All elements of 'when' must be same type."
                if type(when[0]) == int: # .. session numbers.
                    when_func = lambda session: session.number in when
                else: # .. dates.
                    dates = [_toDate(d) for d in when]
                    when_func = lambda session: session.datetime.date() in dates

        valid_sessions = [s for s in self.sessions if s.subject_ID in subject_IDs and when_func(s)]
        
        return valid_sessions       


def _toDate(d): # Convert input to datetime.date object.
    if type(d) is str:
        try:
            return datetime.strptime(d, '%Y-%m-%d').date()
        except ValueError:
            raise ValueError('Unable to convert string to date, format must be YYYY-MM-DD.')
    elif type(d) is datetime:
        return d.date()
    elif type(d) is date:
        return d
    else:
        raise ValueError('Unable to convert input to date.')

#----------------------------------------------------------------------------------
# Session Dataframe
#----------------------------------------------------------------------------------

def session_dataframe(file_path, paired_events={}, pair_end_suffix=None):
    '''Generate a pandas dataframe from a pyControl data file containing the 
    sessions data.  The data frame has columns:
    type : Whether the row contains session 'info', a 'state' entry, 
          'event' or 'print' line.
    name : The name of the state, event or session information in the row.
    time : The time the row occured in ms since the session start.
    duration : The duration in ms of states and paired events (see below).
    value : The contents of 'info' and 'print' rows.

    Optionally events can be specified as coming in pairs corresponding to the
    start and end of an action, e.g. entering and exiting a nosepoke. When a 
    start-event end-event pair occurs in the data, only the start_event generates
    a row in the dataframe, with the end event used to compute the duration. 
    
    Parameters
    ----------
    file_path : path to pyControl data file.
    
    paired_events : Optional dict specifying paired events e.g. 
                    {'poke_1_in':poke_1_out', 'poke_1_in':poke_1_out'}.  
    
    pair_end_suffix : Optional string specifying a suffix used to indicate the
                      end event of paired events that share a common stem e.g.
                      the pair {'poke_1_in':poke_1_out'} would be found 
                      automatically using pair_end_suffix='_out'

    Returns
    -------
    df : session dataframe
    '''

    # Load data from file.
    with open(file_path, 'r') as f:
        print('Importing data file: '+os.path.split(file_path)[1])
        all_lines = [line.strip() for line in f.readlines() if line.strip()]
    
    # Make dataframe.
    state_IDs = eval(next(line for line in all_lines if line[0]=='S')[2:])
    event_IDs = eval(next(line for line in all_lines if line[0]=='E')[2:])
    ID2name = {v: k for k, v in {**state_IDs, **event_IDs}.items()}

    line_dicts = []
    for line in all_lines:
        if line[0] == 'I': # Info line.
            name, value = line[2:].split(' : ')
            line_dicts.append({'type'  : 'info',
                               'name'  : name,
                               'value' : value})
        elif line[0] == 'D': # Data line.
            timestamp, ID = [int(i) for i in line.split(' ')[1:]]
            line_dicts.append({'type' : 'state' if ID in state_IDs.values() else 'event',
                                'name' : ID2name[ID],
                                'time' : int(timestamp)})
        elif line[0] == 'P': # Print line.
            line_dicts.append({'type'  : 'print',
                               'time'  : int(line[2:].split(' ',1)[0]),
                               'value' : line[2:].split(' ',1)[1]})

    df = pd.DataFrame(line_dicts)
    
    # Add state durations.
    df.loc[df['type'] == 'state','duration'] = -df.loc[df['type'] == 'state','time'].diff(-1)

    # Find paired events with specified pair end suffix.
    if pair_end_suffix: 
        end_events = [ev for ev in event_IDs.keys() if ev.endswith(pair_end_suffix)]
        for end_event in end_events:
            stem = end_event[:-len(pair_end_suffix)]
            try:
                start_event = next(ev for ev in event_IDs.keys() if ev.startswith(stem) and ev != end_event)
            except StopIteration:
                continue # No matching start event found.
            paired_events[start_event] = end_event
        
    # Compute paired event durations and remove end events.
    if paired_events:
        end2start = {v:k for k,v in paired_events.items()}
        start_times = {se:None for se in paired_events.keys()}
        start_inds  = {se:None for se in paired_events.keys()}
        end_inds = []
        for i in df.index:
            if df.loc[i,'name'] in paired_events.keys(): # Pair start event.
                start_times[df.loc[i,'name']] = df.loc[i,'time']
                start_inds[ df.loc[i,'name']] = i
            elif df.loc[i,'name'] in paired_events.values(): # Pair end event.
                start_event = end2start[df.loc[i,'name']]
                if start_times[start_event] is not None:
                    df.loc[start_inds[start_event],'duration'] = df.loc[i,'time'] - start_times[start_event]
                    start_times[start_event] = None
                    end_inds.append(i)
        df.drop(index=end_inds, inplace=True)
                     
    # Reset index and set column order.    
    df.reset_index(drop=True)
    df = df.reindex(columns=['type','name','time','duration','value'])
    return df

#----------------------------------------------------------------------------------
# Experiment dataframe
#----------------------------------------------------------------------------------

def experiment_dataframe(folder_path, paired_events={}, pair_end_suffix=None):
    '''Generate a pandas dataframe from a pyControl experiment comprising 
    many session data files in a folder.  The experiment dataframe has the 
    same columns as the session dataframe ('type', 'name', 'time', 'duration',
    'value'), with additional columns specifying the subject_ID, start data and 
    time etc generated from the info lines in the pyControl data file.  Each row
    of the dataframe corresponds to a single state entry, event or print line
    from a single session.

    As with the session_dataframe function, events can optionally  be specified
    as coming in pairs corresponding to the start and end of an action, e.g. 
    entering and exiting a nosepoke. When a start-event end-event pair occurs
    in the data, only the start_event generates a row in the dataframe, with 
    the end event used to compute the duration. 
    
    Parameters
    ----------
    folder_path : path to experiment data folder.
    
    paired_events : Optional dict specifying paired events e.g. 
                    {'poke_1_in':poke_1_out', 'poke_1_in':poke_1_out'}.  
    
    pair_end_suffix : Optional string specifying a suffix used to indicate the
                      end event of paired events that share a common stem e.g.
                      the pair {'poke_1_in':poke_1_out'} would be found 
                      automatically using pair_end_suffix='_out'

    Returns
    -------
    df : session dataframe
    '''
    session_filenames = [f for f in os.listdir(folder_path) if f[-4:] == '.txt']
    session_dataframes = []
    for session_filename in session_filenames:
        # Make session dataframe.
        session_df = session_dataframe(os.path.join(folder_path,session_filename),
            paired_events=paired_events, pair_end_suffix=pair_end_suffix)
        # Convert info rows to columns.
        info_rows = session_df[session_df['type']=='info']
        session_df = session_df[session_df['type']!='info']
        for name,value in zip(info_rows['name'], info_rows['value']):
            session_df[name] = value
        session_dataframes.append(session_df)
    experiment_df = pd.concat(session_dataframes, axis=0)
    return experiment_df

#----------------------------------------------------------------------------------
# Load analog data
#----------------------------------------------------------------------------------

def load_analog_data(file_path):
    '''Load a pyControl analog data file and return the contents as a numpy array
    whose first column is timestamps (ms) and second data values.'''
    with open(file_path, 'rb') as f:
        return np.fromfile(f, dtype='<i').reshape(-1,2)