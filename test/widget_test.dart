import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:psc_mentor/app.dart';
import 'package:psc_mentor/core/api.dart';
import 'package:psc_mentor/core/models.dart';
import 'package:psc_mentor/features/textbooks/textbook_screen.dart';

const _summary = {
  'attempts': 40,
  'accuracy': 0.75,
  'week_attempts': 20,
  'week_accuracy': 0.7,
  'tests_taken': 2,
  'streak_days': 3,
  'revision_due': 4,
  'syllabus_coverage': 0.2,
  'question_bank': 120,
  'subjects': [],
  'weak_topics': [
    {
      'topic_id': 'history.kerala_renaissance',
      'topic': 'Social Reformers',
      'subject_id': 'history',
      'subject': 'History',
      'weight': 8,
      'bank_size': 10,
      'attempts': 6,
      'accuracy': 0.5,
      'last_attempt': '2026-10-27T10:00:00',
    },
  ],
};

const _plan = [
  {
    'id': 1,
    'day': '2026-10-28',
    'kind': 'study',
    'topic_id': 'constitution.rights_duties',
    'topic': 'Fundamental Rights, DPSP, Duties & Citizenship',
    'subject': 'Indian Constitution',
    'subject_id': 'constitution',
    'minutes': 30,
    'done': false,
  },
  {
    'id': 2,
    'day': '2026-10-28',
    'kind': 'daily_test',
    'topic_id': null,
    'topic': null,
    'subject': null,
    'subject_id': null,
    'minutes': 15,
    'done': true,
  },
];

const _test = {
  'id': 7,
  'type': 'daily',
  'title': 'Daily practice',
  'topic_id': null,
  'paper_id': null,
  'question_count': 1,
  'duration_minutes': 15,
  'negative_mark': 1 / 3,
  'created_at': '2026-10-28T09:00:00',
  'submitted_at': null,
  'score': null,
  'max_score': null,
  'correct': null,
  'wrong': null,
  'skipped': null,
  'questions': [
    {
      'id': 11,
      'type': 'verified_pyq',
      'topic_id': 'geography.kerala',
      'stem': 'Which is the longest river in Kerala?',
      'options': ['Bharathapuzha', 'Periyar', 'Pamba', 'Chaliyar'],
      'difficulty': 1,
      'lang': 'en',
      'verification': 'final_key',
      'source_paper_id': 1,
      'source_qno': 4,
    },
  ],
};

Map<String, Object?> _user({required bool diagnosticDone}) => {
      'id': 1,
      'name': 'Anu',
      'login': '9876543210',
      'target_exam': 'degree_prelims',
      'daily_minutes': 120,
      'exam_date': null,
      'language': 'en',
      'diagnostic_test_id': diagnosticDone ? 3 : null,
      'exam': {'name': 'Degree Level Preliminary', 'questions': 100, 'minutes': 75},
      'diagnostic_done': diagnosticDone,
    };

Map<String, Object?> _section(String id, String name, int marks, double? acc, String status, int minutes) => {
      'subject_id': id,
      'subject': name,
      'marks': marks,
      'attempts': 10,
      'accuracy': acc,
      'status': status,
      'weekly_minutes': minutes,
      'expected_marks': 5.0,
      'potential_gain': 4.0,
      'weak_topics': <Object>[],
      'strong_topics': <Object>[],
    };

final _report = {
  'date': '2026-10-28',
  'assessed': true,
  'diagnostic': {'id': 3},
  'daily_minutes': 120,
  'weekly_study_minutes': 540,
  'estimated_score': 41.5,
  'max_score': 100,
  'thresholds': {'strong': 0.7, 'weak': 0.5, 'target': 0.8},
  'sections': [
    _section('english', 'General English', 20, 0.35, 'weak', 150),
    _section('arithmetic', 'Simple Arithmetic', 10, 0.45, 'weak', 75),
    _section('history', 'History', 10, 0.8, 'strong', 35),
  ],
};

void main() {
  late List<String> calls;
  late bool diagnosticDone;

  setUp(() {
    calls = [];
    diagnosticDone = true;
    Api.instance.baseUrl = 'http://test';
    Api.instance.useToken('token');
    Api.instance.client = MockClient((request) async {
      calls.add('${request.method} ${request.url.path}');
      if (request.url.path == '/auth/signup') {
        diagnosticDone = false;
        return http.Response(jsonEncode({'token': 't2', 'user': _user(diagnosticDone: false)}), 200);
      }
      final body = switch (request.url.path) {
        '/today' => {'date': '2026-10-28', 'plan': _plan, 'summary': _summary, 'ai_enabled': false},
        '/me' => _user(diagnosticDone: diagnosticDone),
        '/analysis' => _report,
        '/plan/week' => _plan,
        '/papers/sync' => {'running': false, 'imported': 0, 'failed': 0, 'queued': 0, 'last_run': null},
        '/textbooks/chapters' => [
            {
              'id': 'ncert:keps2:2', 'board': 'NCERT', 'class': 11, 'subject': 'Political Science',
              'book': 'Indian Constitution at Work', 'chapter': 2, 'title': 'Rights in the Indian Constitution',
              'url': 'https://ncert.nic.in/textbook/pdf/keps202.pdf', 'status': 'done', 'error': null, 'questions': 10,
              'topics': [{'topic_id': 'constitution.rights_duties', 'topic': 'Fundamental Rights, DPSP, Duties & Citizenship'}],
            },
            {
              'id': 'ncert:jess2:3', 'board': 'NCERT', 'class': 10, 'subject': 'Social Science',
              'book': 'Understanding Economic Development', 'chapter': 3, 'title': 'Money and Credit',
              'url': 'https://ncert.nic.in/textbook/pdf/jess203.pdf', 'status': 'pending', 'error': null, 'questions': 0,
              'topics': [{'topic_id': 'economics.finance', 'topic': 'RBI, budget, taxes & fiscal policy'}],
            },
          ],
        '/course' => {
            'total_days': 120,
            'today_day': 3,
            'start': '2026-10-26',
            'end': '2027-02-22',
            'days': [
              {
                'day': 3,
                'date': '2026-10-28',
                'kind': 'study',
                'done': false,
                'topics': [
                  {
                    'topic_id': 'constitution.rights_duties',
                    'topic': 'Fundamental Rights, DPSP, Duties & Citizenship',
                    'subject': 'Indian Constitution',
                    'subject_id': 'constitution',
                    'details': 'Fundamental Rights; Directive Principles; Fundamental Duties; citizenship.',
                    'part': 1,
                    'parts': 2,
                    'practised': false,
                  },
                ],
              },
              {'day': 7, 'date': '2026-11-01', 'kind': 'weekly_test', 'done': false, 'topics': <Object>[]},
            ],
          },
        '/topics/constitution.rights_duties/videos' => {
            'topic_id': 'constitution.rights_duties',
            'stale': false,
            'videos': [
              {
                'video_id': 'abc',
                'title': 'Fundamental Rights | Kerala PSC Degree Prelims',
                'channel': 'PSC Talks',
                'views': 1234567,
                'duration_seconds': 1510,
                'thumbnail': null,
                'published_at': '2026-01-01T00:00:00Z',
                'url': 'https://www.youtube.com/watch?v=abc',
              },
            ],
          },
        '/tests' when request.method == 'POST' => _test,
        _ => <String, Object>{},
      };
      return http.Response(jsonEncode(body), 200, headers: {'content-type': 'application/json'});
    });
  });

  Future<void> start(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1400, 2600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(const PscMentorApp());
    await tester.pumpAndSettle();
  }

  testWidgets('signed-out students see the account screen and land on the diagnostic after sign-up',
      (tester) async {
    Api.instance.useToken(null);
    await start(tester);
    expect(find.text('Create account'), findsWidgets);

    await tester.enterText(find.widgetWithText(TextFormField, 'Your name'), 'Anu');
    await tester.enterText(find.widgetWithText(TextFormField, 'Mobile number or email'), '9876543210');
    await tester.enterText(find.widgetWithText(TextFormField, 'Password'), 'secret123');
    await tester.tap(find.widgetWithText(FilledButton, 'Create account'));
    await tester.pumpAndSettle();

    expect(calls, contains('POST /auth/signup'));
    expect(find.textContaining('let\'s find where you stand'), findsOneWidget);
    expect(find.text('Start diagnostic mock'), findsOneWidget);
    expect(find.text('English 20'), findsOneWidget);
  });

  testWidgets('home shows the time plan, today\'s plan and weak areas', (tester) async {
    await start(tester);
    expect(find.textContaining('Anu'), findsOneWidget);
    expect(find.textContaining('Estimated score 41.5 / 100'), findsOneWidget);
    expect(find.text('General English · 2 h 30 min'), findsOneWidget);
    expect(find.text('Indian Constitution'), findsOneWidget);
    expect(find.text('45 minutes'), findsOneWidget);
    expect(find.text('30 minutes left'), findsOneWidget);
    expect(find.textContaining('Social Reformers · 50%'), findsOneWidget);
    expect(find.text('AI mentor is off'), findsOneWidget);
  });

  testWidgets('the strength report lists sections with status and weekly time', (tester) async {
    await start(tester);
    await tester.tap(find.textContaining('Estimated score 41.5'));
    await tester.pumpAndSettle();
    expect(find.text('Strength report'), findsOneWidget);
    expect(find.text('General English'), findsOneWidget);
    expect(find.text('Weak'), findsNWidgets(2));
    expect(find.text('Strong'), findsOneWidget);
    expect(find.textContaining('Study 2 h 30 min a week'), findsOneWidget);
  });

  testWidgets('starting a plan item opens the test screen', (tester) async {
    await start(tester);
    await tester.tap(find.text('Start').first);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(calls, contains('POST /tests'));
    expect(find.text('Which is the longest river in Kerala?'), findsOneWidget);
    expect(find.text('Periyar'), findsOneWidget);
    expect(find.text('15:00'), findsOneWidget);
  });

  testWidgets('a study block shows the most-viewed YouTube lessons for its topic', (tester) async {
    await start(tester);
    await tester.tap(find.byTooltip('Top YouTube lessons').first);
    await tester.pumpAndSettle();
    expect(calls, contains('GET /topics/constitution.rights_duties/videos'));
    expect(find.textContaining('Fundamental Rights | Kerala PSC'), findsOneWidget);
    expect(find.text('PSC Talks · 1.2M views'), findsOneWidget);
    expect(find.text('25:10'), findsOneWidget);
  });

  testWidgets('home shows the course day and the course lists days with their topics', (tester) async {
    await start(tester);
    expect(find.text('Day 3 of 120'), findsOneWidget);
    await tester.tap(find.text('Day 3 of 120'));
    await tester.pumpAndSettle();
    expect(find.text('Day 3 · Wed 28 Oct · Today'), findsOneWidget);
    expect(find.text('Weekly test & revision'), findsOneWidget);
    await tester.tap(find.text('Day 3 · Wed 28 Oct · Today'));
    await tester.pumpAndSettle();
    expect(find.text('Part 1 of 2'), findsOneWidget);
    expect(find.textContaining('Syllabus: Fundamental Rights; Directive Principles'), findsOneWidget);
  });

  testWidgets('the NCERT screen lists chapters with their question counts', (tester) async {
    tester.view.physicalSize = const Size(1400, 2600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(const MaterialApp(home: TextbookScreen()));
    await tester.pumpAndSettle();
    expect(find.text('10 questions from 1 chapters'), findsOneWidget);
    expect(find.text('Rights in the Indian Constitution'), findsOneWidget);
    expect(find.text('Class 11 · Indian Constitution at Work · Ch 2'), findsOneWidget);
    expect(find.text('10 questions'), findsOneWidget);
    expect(find.text('No questions yet'), findsOneWidget);
    expect(find.text('Make questions'), findsOneWidget);
    expect(find.text('Make more'), findsOneWidget);
  });

  test('question source labels', () {
    final raw = (_test['questions']! as List).first as Map<String, dynamic>;
    expect(Question.fromJson(raw).sourceLabel, 'PYQ · final key');
    final upload = Question.fromJson({...raw, 'type': 'uploaded', 'verification': 'ai_solved'});
    expect(upload.sourceLabel, 'Your paper · AI-answered');
  });
}
