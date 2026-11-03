import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

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
                for (final d in entry.value)
                  _DayTile(
                    day: d,
                    today: d.day == course.todayDay,
                    upcoming: course.todayDay != null && d.day > course.todayDay!,
                  ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _DayTile extends StatelessWidget {
  const _DayTile({required this.day, required this.today, required this.upcoming});
  final CourseDay day;
  final bool today;
  final bool upcoming;

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
        onTap: () => _openDay(context, day, upcoming: upcoming),
      ),
    );
  }
}

void _openDay(BuildContext context, CourseDay day, {required bool upcoming}) {
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (sheet) => _DaySheet(day: day, upcoming: upcoming),
  );
}

class _DaySheet extends StatefulWidget {
  const _DaySheet({required this.day, required this.upcoming});
  final CourseDay day;
  final bool upcoming;

  @override
  State<_DaySheet> createState() => _DaySheetState();
}

class _DaySheetState extends State<_DaySheet> {
  late bool _done = widget.day.done;
  late final Set<String> _practised = {
    for (final t in widget.day.topics)
      if (t.practised) t.topicId,
  };

  Future<void> _setDayDone(bool done) async {
    try {
      await Api.instance.setCourseDayDone(widget.day.day, done);
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  Future<void> _setTopicDone(CourseTopic topic, bool done) async {
    final before = (_done, {..._practised});
    setState(() {
      done ? _practised.add(topic.topicId) : _practised.remove(topic.topicId);
      _done = done && _practised.length == widget.day.topics.length;
    });
    try {
      await Api.instance.setCourseTopicDone(widget.day.day, topic.topicId, done);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _done = before.$1;
        _practised
          ..clear()
          ..addAll(before.$2);
      });
      showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final day = widget.day;
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.6,
      maxChildSize: 0.92,
      builder: (context, scroll) => ListView(
        controller: scroll,
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
        children: [
          Text('Day ${day.day} · ${_dateLabel(day.date)}', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          if (!widget.upcoming) ...[
            if (_done)
              OutlinedButton.icon(
                icon: const Icon(Icons.undo),
                label: Text('Day ${day.day} complete · Undo'),
                onPressed: () => _setDayDone(false),
              )
            else
              FilledButton.icon(
                icon: const Icon(Icons.check),
                label: Text('Mark Day ${day.day} complete'),
                onPressed: () => _setDayDone(true),
              ),
            const SizedBox(height: 12),
          ],
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
                      if (!widget.upcoming) ...[
                        const Text('Done'),
                        Checkbox(
                          key: ValueKey('topic-done-${t.topicId}'),
                          value: _practised.contains(t.topicId),
                          onChanged: (v) => _setTopicDone(t, v ?? false),
                        ),
                      ],
                    ]),
                    Text(t.topic, style: Theme.of(context).textTheme.titleMedium),
                    if (t.partLabel.isNotEmpty) Text(t.partLabel, style: Theme.of(context).textTheme.bodySmall),
                    const SizedBox(height: 6),
                    Text('Syllabus: ${t.details}'),
                    _ReadingList(topicId: t.topicId),
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
    );
  }
}

/// The NCERT chapters that teach a topic, opening the chapter PDF.
class _ReadingList extends StatefulWidget {
  const _ReadingList({required this.topicId});
  final String topicId;

  @override
  State<_ReadingList> createState() => _ReadingListState();
}

class _ReadingListState extends State<_ReadingList> {
  // Kept here so that ticking a topic in the sheet doesn't fetch the list again.
  late final _chapters = Api.instance.topicTextbooks(widget.topicId);

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<TextbookChapter>>(
      future: _chapters,
      builder: (context, snap) {
        final chapters = snap.data ?? const [];
        if (chapters.isEmpty) return const SizedBox.shrink();
        return Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Read in ${chapters.first.board}:', style: Theme.of(context).textTheme.labelLarge),
              for (final c in chapters.take(4))
                InkWell(
                  onTap: () => launchUrl(Uri.parse(c.url), mode: LaunchMode.externalApplication),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 3),
                    child: Row(children: [
                      const Icon(Icons.menu_book_outlined, size: 16),
                      const SizedBox(width: 6),
                      Expanded(child: Text('Class ${c.classNo} · ${c.book} · Ch ${c.chapter}: ${c.title}')),
                    ]),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}
