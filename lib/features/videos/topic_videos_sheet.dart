import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api.dart';
import '../../core/models.dart';
import '../../core/ui.dart';

/// Bottom sheet with the most-viewed Kerala PSC lessons on a topic.
Future<void> showTopicVideos(BuildContext context, {required String topicId, required String topic}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.6,
      maxChildSize: 0.9,
      builder: (context, scroll) => _VideosList(topicId: topicId, topic: topic, scroll: scroll),
    ),
  );
}

class _VideosList extends StatefulWidget {
  const _VideosList({required this.topicId, required this.topic, required this.scroll});
  final String topicId;
  final String topic;
  final ScrollController scroll;

  @override
  State<_VideosList> createState() => _VideosListState();
}

class _VideosListState extends State<_VideosList> {
  late Future<List<TopicVideo>> _videos = Api.instance.topicVideos(widget.topicId);

  Future<void> _open(TopicVideo v) async {
    final ok = await launchUrl(Uri.parse(v.url), mode: LaunchMode.externalApplication);
    if (!ok && mounted) showError(context, 'Could not open YouTube.');
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      controller: widget.scroll,
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
      children: [
        Text('Top videos: ${widget.topic}', style: theme.textTheme.titleMedium),
        const SizedBox(height: 4),
        Text('The most-viewed Kerala PSC lessons on YouTube for this topic.', style: theme.textTheme.bodySmall),
        const SizedBox(height: 12),
        FutureBuilder<List<TopicVideo>>(
          future: _videos,
          builder: (context, snap) {
            if (snap.hasError) {
              return ErrorCard(snap.error!,
                  onRetry: () => setState(() => _videos = Api.instance.topicVideos(widget.topicId)));
            }
            if (!snap.hasData) {
              return const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator()));
            }
            final list = snap.data!;
            if (list.isEmpty) return const Text('No PSC lessons found on YouTube for this topic yet.');
            return Column(children: [
              for (final (i, v) in list.indexed)
                Card(
                  clipBehavior: Clip.antiAlias,
                  child: InkWell(
                    onTap: () => _open(v),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Stack(children: [
                          SizedBox(
                            width: 140,
                            height: 79,
                            child: v.thumbnail == null
                                ? const ColoredBox(color: Colors.black12, child: Icon(Icons.ondemand_video))
                                : Image.network(v.thumbnail!, fit: BoxFit.cover,
                                    errorBuilder: (_, __, ___) =>
                                        const ColoredBox(color: Colors.black12, child: Icon(Icons.ondemand_video))),
                          ),
                          Positioned(
                            right: 4,
                            bottom: 4,
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
                              color: Colors.black87,
                              child: Text(v.durationLabel, style: const TextStyle(color: Colors.white, fontSize: 11)),
                            ),
                          ),
                        ]),
                        Expanded(
                          child: Padding(
                            padding: const EdgeInsets.all(10),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('${i + 1}. ${v.title}', maxLines: 2, overflow: TextOverflow.ellipsis,
                                    style: theme.textTheme.titleSmall),
                                const SizedBox(height: 4),
                                Text('${v.channel} · ${v.viewsLabel}', style: theme.textTheme.bodySmall),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
            ]);
          },
        ),
      ],
    );
  }
}
