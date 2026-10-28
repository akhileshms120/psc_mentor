import 'package:flutter/material.dart';

import '../../core/api.dart';
import '../../core/models.dart';
import '../../core/ui.dart';
import '../analysis/analysis_screen.dart';
import '../course/course_screen.dart';
import '../mentor/mentor_screen.dart';
import '../profile/profile_screen.dart';
import '../tests/test_runner.dart';
import '../videos/topic_videos_sheet.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  void _openProfile(BuildContext context) =>
      Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const ProfileScreen()));

  @override
  Widget build(BuildContext context) {
    final settings = IconButton(
      tooltip: 'Profile & settings',
      icon: const Icon(Icons.settings_outlined),
      onPressed: () => _openProfile(context),
    );
    return Loader<(Today, User, List<PlanItem>, StrengthReport, Course)>(
      load: () async => (
        await Api.instance.today(),
        await Api.instance.me(),
        await Api.instance.week(),
        await Api.instance.analysis(),
        await Api.instance.course(),
      ),
      builder: (context, data, reload) {
        final (today, student, week, report, course) = data;
        final s = today.summary;
        final daysLeft = student.daysToExam(DateTime.now());
        final minutes = today.plan.fold<int>(0, (sum, p) => sum + p.minutes);
        final left = today.plan.where((p) => !p.done).fold<int>(0, (sum, p) => sum + p.minutes);
        return PageFrame(
          title: '${_greeting()}, ${student.name}',
          subtitle: daysLeft == null
              ? 'Set your exam date in settings so the mentor can pace your preparation.'
              : daysLeft >= 0
                  ? '$daysLeft days to the ${student.examName} exam.'
                  : 'Your exam date has passed. Update it in settings.',
          actions: [settings],
          onRefresh: reload,
          children: [
            if (!today.aiEnabled)
              const Card(
                child: ListTile(
                  leading: Icon(Icons.info_outline),
                  title: Text('AI mentor is off'),
                  subtitle: Text('Tests and tracking work from the question bank. Add an AI key on the server '
                      '(APINEX_API_KEY or GEMINI_API_KEY) to chat with the mentor, generate new questions and '
                      'read Malayalam papers.'),
                ),
              ),
            CardGrid(children: [
              InfoCard(title: 'Today\'s target', value: '$minutes minutes', icon: Icons.schedule,
                  caption: left == 0 ? 'All done for today' : '$left minutes left'),
              InfoCard(title: 'Accuracy (7 days)', value: pct(s.weekAccuracy), icon: Icons.track_changes,
                  caption: '${s.weekAttempts} questions · ${s.streakDays}-day streak'),
              InfoCard(title: 'Revision due', value: '${s.revisionDue} questions', icon: Icons.replay,
                  caption: '${s.questionBank} questions in your bank'),
            ]),
            CourseCard(course: course),
            _TimePlanCard(report: report),
            const SectionTitle('Today\'s plan'),
            for (final item in today.plan) _PlanTile(item: item, revisionDue: s.revisionDue),
            if (s.weakTopics.isNotEmpty) ...[
              const SectionTitle('Weak areas to improve'),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final t in s.weakTopics)
                    ActionChip(
                      avatar: const Icon(Icons.trending_down, size: 18),
                      label: Text('${t.topic} · ${pct(t.accuracy)}'),
                      onPressed: () => startTest(context, () => Api.instance.createTest('topic', topicId: t.topicId)),
                    ),
                ],
              ),
            ],
            const SectionTitle('This week'),
            _WeekStrip(week: week, today: today.date),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                icon: const Icon(Icons.autorenew),
                label: const Text('Re-plan rest of week'),
                onPressed: () async {
                  try {
                    await Api.instance.regeneratePlan();
                  } catch (e) {
                    if (context.mounted) showError(context, e);
                  }
                },
              ),
            ),
          ],
        );
      },
    );
  }

  static String _greeting() {
    final hour = DateTime.now().hour;
    return hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
  }
}

class _TimePlanCard extends StatelessWidget {
  const _TimePlanCard({required this.report});
  final StrengthReport report;

  @override
  Widget build(BuildContext context) {
    final top = [...report.sections]..sort((a, b) => b.weeklyMinutes.compareTo(a.weeklyMinutes));
    final weak = report.sections.where((s) => s.status == 'weak').length;
    final strong = report.sections.where((s) => s.status == 'strong').length;
    return Card(
      child: InkWell(
        onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const AnalysisScreen())),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                const Icon(Icons.insights),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    report.estimatedScore == null
                        ? 'Your weekly time plan'
                        : 'Estimated score ${report.estimatedScore!.toStringAsFixed(1)} / ${report.maxScore} · '
                            '$strong strong, $weak weak',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                const Icon(Icons.chevron_right),
              ]),
              const SizedBox(height: 10),
              Text('This week, spend most time on:', style: Theme.of(context).textTheme.labelLarge),
              const SizedBox(height: 6),
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final s in top.take(4))
                  Chip(
                    avatar: CircleAvatar(backgroundColor: statusColor(context, s.status), radius: 6),
                    label: Text('${s.subject} · ${hoursMinutes(s.weeklyMinutes)}'),
                  ),
              ]),
            ],
          ),
        ),
      ),
    );
  }
}

class _PlanTile extends StatelessWidget {
  const _PlanTile({required this.item, required this.revisionDue});
  final PlanItem item;
  final int revisionDue;

  Future<void> _start(BuildContext context) {
    final api = Api.instance;
    return switch (item.kind) {
      'study' => startTest(context, () => api.createTest('topic', topicId: item.topicId)),
      'revision' => startTest(context, () => api.createTest('mistakes')),
      'daily_test' => startTest(context, () => api.createTest('daily')),
      'weekly_test' => startTest(context, () => api.createTest('weekly')),
      _ => startTest(context, () => api.createTest('monthly')),
    };
  }

  @override
  Widget build(BuildContext context) {
    final nothingToRevise = item.kind == 'revision' && revisionDue == 0 && !item.done;
    return Card(
      child: ListTile(
        leading: Checkbox(
          value: item.done,
          onChanged: (_) async {
            try {
              await Api.instance.togglePlanItem(item.id);
            } catch (e) {
              if (context.mounted) showError(context, e);
            }
          },
        ),
        title: Text(item.title, style: item.done ? const TextStyle(decoration: TextDecoration.lineThrough) : null),
        subtitle: Text(nothingToRevise ? 'Nothing due yet. Wrong answers will appear here.' : '${item.detail} · ${item.minutes} min'),
        trailing: Wrap(
          spacing: 4,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            if (item.kind == 'study' && item.topicId != null)
              IconButton(
                tooltip: 'Top YouTube lessons',
                icon: const Icon(Icons.smart_display_outlined),
                onPressed: () => showTopicVideos(context, topicId: item.topicId!, topic: item.topic ?? ''),
              ),
            if (item.kind == 'study')
              IconButton(
                tooltip: 'Learn with mentor',
                icon: const Icon(Icons.chat_outlined),
                onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                  builder: (_) => MentorScreen(
                    standalone: true,
                    initialMessage: 'Teach me today\'s topic "${item.topic}" (${item.subject}) for Kerala PSC.',
                  ),
                )),
              ),
            FilledButton.tonal(
              onPressed: nothingToRevise ? null : () => _start(context),
              child: Text(item.kind == 'study' ? 'Practice' : 'Start'),
            ),
          ],
        ),
      ),
    );
  }
}

class _WeekStrip extends StatelessWidget {
  const _WeekStrip({required this.week, required this.today});
  final List<PlanItem> week;
  final String today;

  static const _days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  @override
  Widget build(BuildContext context) {
    final byDay = <String, List<PlanItem>>{};
    for (final p in week) {
      byDay.putIfAbsent(p.day, () => []).add(p);
    }
    final days = byDay.keys.toList()..sort();
    final scheme = Theme.of(context).colorScheme;
    return Card(
      child: Column(
        children: [
          for (final day in days)
            ListTile(
              dense: true,
              selected: day == today,
              selectedTileColor: scheme.primaryContainer.withValues(alpha: 0.4),
              leading: Text(_days[DateTime.parse(day).weekday - 1], style: Theme.of(context).textTheme.titleSmall),
              title: Text(byDay[day]!
                  .where((p) => p.kind != 'revision' && p.kind != 'daily_test')
                  .map((p) => p.kind == 'study' ? p.topic : p.title)
                  .join('  ·  ')),
              trailing: Text('${byDay[day]!.where((p) => p.done).length}/${byDay[day]!.length}'),
            ),
        ],
      ),
    );
  }
}
