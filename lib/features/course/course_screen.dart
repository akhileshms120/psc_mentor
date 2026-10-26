import 'package:flutter/material.dart';

import '../../core/api.dart';
import '../../core/models.dart';
import '../../core/ui.dart';
import '../mentor/mentor_screen.dart';
import '../tests/test_runner.dart';
import '../videos/topic_videos_sheet.dart';

const _weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const _months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

String _dateLabel(String iso) {
  final d = DateTime.parse(iso);
  return '${_weekdays[d.weekday - 1]} ${d.day} ${_months[d.month - 1]}';
}

/// "Day 12 of 120" card for Home and Study; opens the full course.
class CourseCard extends StatelessWidget {
  const CourseCard({super.key, required this.course});
  final Course course;

  @override
  Widget build(BuildContext context) {
    final today = course.days.where((d) => d.day == course.todayDay).firstOrNull;
    final done = course.days.where((d) => d.done).length;
    return Card(
      child: InkWell(
        onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const CourseScreen())),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                const Icon(Icons.route_outlined),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    today == null ? 'Your ${course.totalDays}-day course' : 'Day ${today.day} of ${course.totalDays}',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                const Icon(Icons.chevron_right),
              ]),
              const SizedBox(height: 6),
              Text(today?.summary ?? 'See what to study each day until the exam.'),
              const SizedBox(height: 8),
              LinearProgressIndicator(value: course.totalDays == 0 ? 0 : done / course.totalDays),
            ],
          ),
        ),
      ),
    );
  }
}

class CourseScreen extends StatelessWidget {
  const CourseScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Day-by-day course')),
      body: Loader<Course>(
        load: Api.instance.course,
        builder: (context, course, reload) {
          final weeks = <int, List<CourseDay>>{};
          for (final d in course.days) {
            weeks.putIfAbsent((d.day - 1) ~/ 7, () => []).add(d);
          }
          return PageFrame(
            title: 'Your ${course.totalDays}-day plan to the exam',
            subtitle: 'Every topic of the Degree Level Prelims syllabus, in order. Weak sections and the '
                'sections with more marks get more days. Sundays are test and revision days, and the last '
                'days before the exam are full mocks.',
            onRefresh: reload,
            children: [
              for (final entry in weeks.entries) ...[
                SectionTitle('Week ${entry.key + 1}'),
                for (final d in entry.value) _DayTile(day: d, today: d.day == course.todayDay),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _DayTile extends StatelessWidget {
  const _DayTile({required this.day, required this.today});
  final CourseDay day;
  final bool today;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      color: today ? scheme.primaryContainer : null,
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: day.done ? Colors.green.shade600 : null,
          foregroundColor: day.done ? Colors.white : null,
          child: day.done ? const Icon(Icons.check) : Text('${day.day}'),
        ),
        title: Text('Day ${day.day} · ${_dateLabel(day.date)}${today ? ' · Today' : ''}'),
        subtitle: Text(day.summary),
        onTap: () => _openDay(context, day),
      ),
    );
  }
}

void _openDay(BuildContext context, CourseDay day) {
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (sheet) => DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.6,
      maxChildSize: 0.92,
      builder: (context, scroll) => ListView(
        controller: scroll,
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
        children: [
          Text('Day ${day.day} · ${_dateLabel(day.date)}', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          if (day.topics.isEmpty) ...[
            Text(day.summary),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: () => startTest(context, () => Api.instance.createTest(switch (day.kind) {
                    'mock' => 'monthly',
                    'weekly_test' => 'weekly',
                    _ => 'mistakes',
                  })),
              child: Text(switch (day.kind) {
                'mock' => 'Start full mock',
                'weekly_test' => 'Start weekly test',
                _ => 'Retest my mistakes',
              }),
            ),
          ],
          for (final t in day.topics)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Expanded(child: Text(t.subject, style: Theme.of(context).textTheme.labelLarge)),
                      if (t.practised) const Icon(Icons.check_circle, color: Colors.green, size: 18),
                    ]),
                    Text(t.topic, style: Theme.of(context).textTheme.titleMedium),
                    if (t.partLabel.isNotEmpty) Text(t.partLabel, style: Theme.of(context).textTheme.bodySmall),
                    const SizedBox(height: 6),
                    Text('Syllabus: ${t.details}'),
                    const SizedBox(height: 8),
                    Wrap(spacing: 8, runSpacing: 4, children: [
                      FilledButton.tonal(
                        onPressed: () => startTest(context, () => Api.instance.createTest('topic', topicId: t.topicId)),
                        child: const Text('Practice test'),
                      ),
                      OutlinedButton.icon(
                        icon: const Icon(Icons.smart_display_outlined),
                        label: const Text('Videos'),
                        onPressed: () => showTopicVideos(context, topicId: t.topicId, topic: t.topic),
                      ),
                      OutlinedButton.icon(
                        icon: const Icon(Icons.chat_outlined),
                        label: const Text('Learn'),
                        onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                          builder: (_) => MentorScreen(
                            standalone: true,
                            initialMessage: 'Teach me "${t.topic}" (${t.subject}) for the Kerala PSC Degree Prelims'
                                '${t.parts > 1 ? ', part ${t.part} of ${t.parts}' : ''}. The syllabus lists: ${t.details}',
                          ),
                        )),
                      ),
                    ]),
                  ],
                ),
              ),
            ),
        ],
      ),
    ),
  );
}
