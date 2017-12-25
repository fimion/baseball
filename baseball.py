import collections
import re
import textwrap

import pytz

import constants
import stats


def strip_this_suffix(pattern, suffix, input_str):
    match = re.search(pattern, input_str)
    while match:
        start = match.start()
        end = match.end()
        str_beginning = input_str[:start]
        str_middle = re.sub(suffix, '.', input_str[start:end])
        str_end = input_str[end:]
        input_str = str_beginning + str_middle + str_end
        match = re.search(pattern, input_str)

    input_str = re.sub(suffix, '', input_str)

    return input_str.strip()

def strip_suffixes(input_str):
    input_str = strip_this_suffix(r' Jr\.\s+[A-Z]', r' Jr\.', input_str)
    input_str = strip_this_suffix(r' Sr\.\s+[A-Z]', r' Sr\.', input_str)
    input_str = re.sub(r' II', '', input_str)
    input_str = re.sub(r' III', '', input_str)
    input_str = re.sub(r' IV', '', input_str)
    input_str = re.sub(r' St\. ', ' St ', input_str)

    return input_str


class PlayerAppearance(object):
    def __init__(self, player_obj, position, start_inning_num,
                 start_inning_half, start_inning_batter_num):
        self.player_obj = player_obj
        self.position = position
        self.start_inning_num = start_inning_num
        self.start_inning_half = start_inning_half
        self.start_inning_batter_num = start_inning_batter_num

        self.end_inning_num = None
        self.end_inning_half = None
        self.end_inning_batter_num = None
        self.pitcher_credit_code = None

    def __repr__(self):
        start_inning_str = '{}-{}'.format(self.start_inning_num,
                                          self.start_inning_half,)

        return_str = '{}\n'.format(str(self.player_obj))

        if self.player_obj.era is not None:
            return_str += '    {}\n'.format(self.player_obj.pitching_stats())

        return_str += (
            '    {}\n'
            '    Entered:     {:12} before batter #{}'
            '    (position {})\n'
        ).format(
            self.player_obj.hitting_stats(),
            start_inning_str,
            self.start_inning_batter_num,
            self.position
        )

        if self.end_inning_num:
            end_inning_str = '{}-{}'.format(self.end_inning_num,
                                            self.end_inning_half)

            return_str += (
                '    Exited:      {:12} before batter #{}\n'
            ).format(
                end_inning_str,
                self.end_inning_batter_num
            )

        return return_str


class Player(object):
    def __init__(self, last_name, first_name, mlb_id, obp, slg, number):
        self.last_name = last_name
        self.first_name = first_name
        self.mlb_id = mlb_id
        self.obp = obp
        self.slg = slg
        self.number = number

        self.era = None

    def full_name(self):
        return '{} {}'.format(self.first_name, self.last_name)

    def hitting_stats(self):
        if self.obp and self.slg:
            return_str = 'OBP: {}   SLG: {}'.format('%.3f' % self.obp,
                                                    '%.3f' % self.slg)
        else:
            return_str = ''

        return return_str

    def pitching_stats(self):
        return 'ERA: {}'.format('%.2f' % self.era)

    def __repr__(self):
        return_str = ''
        if self.number is not None:
            return_str += '{:2} '.format(self.number)
        else:
            return_str += '   '

        return_str += '{}'.format(self.full_name())

        return return_str


class Team(object):
    def __init__(self, name, abbreviation):
        self.name = name
        self.abbreviation = abbreviation

        self.pitcher_list = []
        self.batting_order_list_list = [None] * 9
        self.player_id_dict = {}
        self.player_name_dict = {}
        self.player_last_name_dict = {}

    def lookup_player(self, player_name):
        if player_name in self.player_name_dict:
            player = self.player_name_dict[player_name]
        else:
            player_name = re.sub(r' Jr$', '', player_name.strip(' .'))
            player_name = re.sub(r' Sr$', '', player_name.strip(' .'))
            player_name = re.sub(r' II$', '', player_name.strip())
            player_name = re.sub(r' III$', '', player_name.strip())
            player_name = re.sub(r' IV$', '', player_name.strip())

            player_name = strip_suffixes(player_name.strip())
            first_name_initial = player_name[0]
            last_name = player_name.split()[-1]

            initial_last_name = first_name_initial + last_name
            player = self.player_last_name_dict[initial_last_name]

        return player

    def __repr__(self):
        return_str = (
            '{}\n# {} ({}) #\n{}\n\n'
            '---------\n'
            ' Batters \n'
            '---------\n'
        ).format(
            '#' * (len(self.name) + 10),
            self.name.upper(),
            self.abbreviation,
            '#' * (len(self.name) + 10)
        )

        for batter_list in self.batting_order_list_list:
            return_str += '{}\n'.format(
                batter_list
            )

        return_str += (
            '\n----------\n'
            ' Pitchers \n'
            '----------\n'
            '{}\n\n'
        ).format(
            self.pitcher_list
        )

        return return_str


class Game(object):
    def __init__(self, home_team, away_team, location, game_date_str,
                 first_pitch_datetime=None, last_pitch_datetime=None,
                 inning_list=None):
        self.home_team = home_team
        self.away_team = away_team
        self.location = location or ''
        self.game_date_str = game_date_str
        self.first_pitch_datetime = first_pitch_datetime
        self.last_pitch_datetime = last_pitch_datetime
        self.inning_list = inning_list or []

        self.away_batter_box_score_dict = None
        self.home_batter_box_score_dict = None
        self.away_pitcher_box_score_dict = None
        self.home_pitcher_box_score_dict = None
        self.away_team_stats = None
        self.home_team_stats = None
        self.first_pitch_str = ''
        self.last_pitch_str = ''

    def set_gametimes(self):
        if self.first_pitch_datetime:
            self.first_pitch_str = self.first_pitch_datetime.astimezone(
                pytz.timezone(
                    constants.STADIUM_TIMEZONE_DICT.get(self.location,
                                                        'America/New_York')
                )
            ).strftime(
                '%a %b %d %Y, %-I:%M %p'
            )
        else:
            self.first_pitch_str = ''

        if self.last_pitch_datetime:
            self.last_pitch_str = self.last_pitch_datetime.astimezone(
                pytz.timezone(
                    constants.STADIUM_TIMEZONE_DICT.get(self.location,
                                                        'America/New_York')
                )
            ).strftime(
                ' - %-I:%M %p %Z'
            )
        else:
            self.last_pitch_str = ''

    def set_pitching_box_score_dict(self):
        self.away_pitcher_box_score_dict = collections.OrderedDict([])
        self.home_pitcher_box_score_dict = collections.OrderedDict([])

        tuple_list = [
            (self.away_pitcher_box_score_dict, self.away_team, 'bottom'),
            (self.home_pitcher_box_score_dict, self.home_team, 'top'),
        ]

        for box_score_dict, team, inning_half_str in tuple_list:
            for pitcher_appearance in team.pitcher_list:
                pitcher = pitcher_appearance.player_obj
                box_score_dict[pitcher] = (
                    stats.get_all_pitcher_stats(self,
                                                team,
                                                pitcher,
                                                inning_half_str)
                )

    def set_batting_box_score_dict(self):
        self.away_batter_box_score_dict = collections.OrderedDict([])
        self.home_batter_box_score_dict = collections.OrderedDict([])

        tuple_list = [
            (self.away_batter_box_score_dict, self.away_team, 'top'),
            (self.home_batter_box_score_dict, self.home_team, 'bottom'),
        ]

        for box_score_dict, team, inning_half_str in tuple_list:
            for batting_order_list in team.batting_order_list_list:
                for batter_appearance in batting_order_list:
                    batter = batter_appearance.player_obj
                    if batter not in box_score_dict:
                        box_score_dict[batter] = (
                            stats.get_all_batter_stats(self,
                                                       batter,
                                                       inning_half_str)
                        )

            box_score_dict['TOTAL'] = stats.get_box_score_total(box_score_dict)

    def set_team_stats(self):
        self.away_team_stats = stats.get_team_stats(self, 'top')
        self.home_team_stats = stats.get_team_stats(self, 'bottom')

    def __repr__(self):
        return_str = '{}\n'.format(self.location)
        if self.first_pitch_str and self.last_pitch_str:
            return_str += '{}{}\n\n'.format(self.first_pitch_str,
                                            self.last_pitch_str)
        else:
            return_str += '{}\n\n'.format(self.game_date_str)

        dict_list = [self.away_batter_box_score_dict,
                     self.away_pitcher_box_score_dict,
                     self.home_batter_box_score_dict,
                     self.home_pitcher_box_score_dict]

        for this_dict in dict_list:
            for name, tup in this_dict.items():
                return_str += '{!s:20s} {}\n'.format(name, str(tup))

            return_str += '\n'

        return_str += 'Away Team ({}): {}\nHome Team ({}): {}\n'.format(
            self.away_batter_box_score_dict['TOTAL'].R,
            str(self.away_team_stats),
            self.home_batter_box_score_dict['TOTAL'].R,
            str(self.home_team_stats)
        )

        return_str += '{}AT\n\n{}'.format(
            self.away_team,
            self.home_team
        )

        for i, inning in enumerate(self.inning_list):
            inning_number = i + 1
            return_str += (
                (' ' * 33) + '############\n' +
                (' ' * 33) + '# INNING {} #\n' +
                (' ' * 33) + '############\n\n{}\n\n'
            ).format(
                inning_number,
                inning
            )

        return return_str


class Inning(object):
    def __init__(self, top_half_appearance_list, bottom_half_appearance_list):
        self.top_half_appearance_list = top_half_appearance_list
        self.bottom_half_appearance_list = bottom_half_appearance_list
        (self.top_half_inning_stats,
         self.bottom_half_inning_stats) = (
             stats.get_half_inning_stats(top_half_appearance_list,
                                         bottom_half_appearance_list)
         )

    def __repr__(self):
        return (
            ('-' * 32) + ' TOP OF INNING ' + ('-' * 32) + '\n{}\n{}\n\n' +
            ('-' * 30) + ' BOTTOM OF INNING ' + ('-' * 31) + '\n{}\n{}'
        ).format(
            self.top_half_inning_stats,
            self.top_half_appearance_list,
            self.bottom_half_inning_stats,
            self.bottom_half_appearance_list
        )


class PlateAppearance(object):
    def __init__(self, batting_team, plate_appearance_description,
                 plate_appearance_summary, pitcher, batter, inning_outs,
                 scoring_runners_list, runners_batted_in_list, event_list):
        self.batting_team = batting_team
        self.event_list = event_list or []
        self.plate_appearance_description = plate_appearance_description
        self.plate_appearance_summary = plate_appearance_summary
        self.pitcher = pitcher
        self.batter = batter
        self.inning_outs = inning_outs
        self.scoring_runners_list = scoring_runners_list
        self.runners_batted_in_list = runners_batted_in_list

        self.out_runners_list = self.get_out_runners_list()
        self.hit_location = self.get_hit_location()
        self.error_str = self.get_error_str()
        (self.got_on_base,
         self.scorecard_summary) = self.get_on_base_and_summary()

    @staticmethod
    def process_defense_predicate_list(defense_player_order):
        defense_code_order = []
        for defense_position in defense_player_order:
            if defense_position in constants.POSITION_CODE_DICT:
                defense_code_order.append(
                    str(constants.POSITION_CODE_DICT[defense_position])
                )
            else:
                if defense_position.strip(' .') not in ['1st', '2nd', '3rd']:
                    raise ValueError(
                        '{} not in position code dict'.format(defense_position)
                    )

        return defense_code_order

    @staticmethod
    def get_defense_player_order(defense_predicate_list):
        defense_player_order = []
        for this_position in defense_predicate_list:
            if 'deep' in this_position:
                this_position = this_position.replace('deep', '').strip()

            if 'shallow' in this_position:
                this_position = this_position.replace('shallow', '').strip()

            this_position = this_position.split()[0].split('-')[0]
            defense_player_order.append(this_position)

        return defense_player_order

    @staticmethod
    def get_defense_predicate_list(description_str):
        if ('caught stealing' in description_str or
                'on fan interference' in description_str or
                'picks off' in description_str or
                'wild pitch by' in description_str):
            defense_predicate_list = []
        elif 'catcher interference by' in description_str:
            defense_predicate_list = ['catcher']
        elif 'fielded by' in description_str:
            description_str = description_str.split(' fielded by ')[1]
            defense_predicate_list = [description_str]
        elif ', ' in description_str and ' to ' in description_str:
            description_str = description_str.split(', ')[1]
            defense_predicate_list = description_str.split(' to ')
        elif  ' to ' in description_str:
            defense_predicate_list = description_str.split(' to ')[1:]
        else:
            defense_predicate_list = []

        if 'error by' in description_str:
            description_str = description_str.split(' error by ')[1]
            defense_predicate_list = [description_str]

        return defense_predicate_list

    @classmethod
    def get_defense_code_order(cls, description_str):
        defense_predicate_list = cls.get_defense_predicate_list(description_str)

        defense_player_order = cls.get_defense_player_order(
            defense_predicate_list
        )

        defense_code_order = cls.process_defense_predicate_list(
            defense_player_order
        )

        return defense_code_order

    @classmethod
    def get_defense_suffix(cls, suffix_str):
        search = re.search(
            r'(?:out at|(?:was )?picked off and caught stealing|'
            r'(?:was )?caught stealing|(?:was )?picked off|'
            r'(?:was )?doubled off)'
            r'[1-3,h][snro][tdm][e]?[\w\s]*, ',
            suffix_str
        )

        if search:
            suffix_str = suffix_str[search.start():]
            suffix_code_order = cls.get_defense_code_order(suffix_str)
            defense_suffix = ' (' + '-'.join(suffix_code_order) + ')'
        else:
            defense_suffix = ''

        return defense_suffix

    def get_out_runners_list(self):
        description = strip_suffixes(self.plate_appearance_description)
        runner_name_list = re.findall(
            (r'([A-Z][\w\'-]+\s+(?:[A-Z,a-z][\w\'-]+\s+)?'
             r'(?:[A-Z,a-z][\w\'-]+\s+)?[A-Z][\w\'-]+)\s+'
             r'(?:out at|(?:was )?picked off and caught stealing|'
             r'(?:was )?caught stealing|(?:was )?picked off|'
             r'(?:was )?doubled off)'
             r' +(\w+)'),
            description
        )

        runner_tuple_list = []
        for name, base in runner_name_list:
            search_pattern = re.escape(name) + r' (?:was )?doubled off'
            if re.findall(search_pattern, description):
                base = constants.INCREMENT_BASE_DICT[base]

            runner_tuple_list.append(
                (self.batting_team.lookup_player(name), base)
            )

        return runner_tuple_list

    def get_throws_str(self):
        description_str = strip_suffixes(self.plate_appearance_description)
        suffix_str = ''

        if '. ' in description_str:
            description_str, suffix_str = description_str.split('. ', 1)

        if ', deflected' in description_str:
            description_str = description_str.split(', deflected')[0]

        if ', assist' in description_str:
            description_str = description_str.split(', assist')[0]

        if ': ' in description_str:
            description_str = description_str.split(': ')[1]

        defense_code_order = self.get_defense_code_order(description_str)
        defense_str = '-'.join(defense_code_order)
        defense_suffix = self.get_defense_suffix(suffix_str)

        return defense_str, defense_suffix

    def get_hit_location(self):
        play_str = self.get_play_str()
        throws_str, _ = self.get_throws_str()

        if throws_str and play_str not in constants.NO_HIT_CODE_LIST:
            hit_location = play_str + throws_str[0]
        else:
            hit_location = None

        return hit_location

    def get_play_str(self):
        description_str = strip_suffixes(self.plate_appearance_description)
        if '. ' in description_str:
            description_str = description_str.split('. ')[0]

        code = None
        for keyword, this_code in constants.PLAY_CODE_ORDERED_DICT.items():
            if keyword in description_str:
                code = this_code

        if self.plate_appearance_summary == 'Fan interference':
            code = 'FI'

        if not code:
            disqualified_description = ('out at' in description_str or
                                        'singles' in description_str or
                                        'doubles' in description_str or
                                        'triples' in description_str or
                                        'hits a home run' in description_str or
                                        'ejected' in description_str)

            if disqualified_description:
                code = ''
            else:
                raise ValueError(
                    'No keyword found in plate description: {}'.format(
                        self.plate_appearance_description
                    )
                )

        return code

    def get_error_str(self):
        error_str = None
        if 'error' in self.plate_appearance_description:
            description_str = self.plate_appearance_description
            description_str = description_str.split(' error by ')[1]
            defense_player = description_str.split()[0]
            defense_code = str(constants.POSITION_CODE_DICT[defense_player])
            error_str = 'E' + defense_code
        elif 'catcher interference' in self.plate_appearance_description:
            error_str = 'E2'

        return error_str

    def get_on_base_and_summary(self):
        throws_str, suffix_str = self.get_throws_str()
        if self.plate_appearance_summary in constants.ON_BASE_SUMMARY_DICT:
            on_base = True
            scorecard_summary = (
                constants.ON_BASE_SUMMARY_DICT[self.plate_appearance_summary] +
                suffix_str
            )
        else:
            on_base = False
            scorecard_summary = (
                self.get_play_str() + throws_str + suffix_str
            )

        return on_base, scorecard_summary

    def __repr__(self):
        wrapper = textwrap.TextWrapper(width=80, subsequent_indent=' '*17)

        description_str = ' Description:    {}'.format(
            self.plate_appearance_description
        )

        return_str = ('\n'
                      ' Scorecard:      {}\n'
                      ' Hit location:   {}\n'
                      ' Pitcher:        {}\n'
                      ' Batter:         {}\n'
                      ' Got on base:    {}\n'
                      ' Fielding Error: {}\n'
                      ' Out Runners:    {}\n'
                      ' Scoring Runners:{}\n'
                      ' Runs Batted In: {}\n'
                      ' Inning Outs:    {}\n'
                      ' Summary:        {}\n'
                      '{}\n'
                      ' Events:\n').format(self.scorecard_summary,
                                           self.hit_location,
                                           self.pitcher,
                                           self.batter,
                                           self.got_on_base,
                                           self.error_str,
                                           self.out_runners_list,
                                           self.scoring_runners_list,
                                           self.runners_batted_in_list,
                                           self.inning_outs,
                                           self.plate_appearance_summary,
                                           wrapper.fill(description_str))

        for event in self.event_list:
            return_str += '     {}\n'.format(event)

        return return_str
