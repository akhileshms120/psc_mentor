// Data classes mirroring the PSC Mentor backend's JSON.

typedef Json = Map<String, dynamic>;

double? _pct(Object? v) => v == null ? null : (v as num).toDouble();

class User {
  User.fromJson(Json j)
      : id = j['id'] as int,
        name = j['name'] as String,
        login = j['login'] as String,
        dailyMinutes = j['daily_minutes'] as int,
        examDate = j['exam_date'] as String?,
        language = j['language'] as String,
        examName = (j['exam'] as Json)['name'] as String,
        examQuestions = (j['exam'] as Json)['questions'] as int,
        examMinutes = (j['exam'] as Json)['minutes'] as int,
        diagnosticDone = j['diagnostic_done'] as bool;

  final int id;
  final String name;
  final String login;
  final int dailyMinutes;
  final String? examDate;
  final String language;
  final String examName;
  final int examQuestions;
  final int examMinutes;
  final bool diagnosticDone;

  int? daysToExam(DateTime today) {
    if (examDate == null) return null;
    final exam = DateTime.tryParse(examDate!);
    if (exam == null) return null;
    return exam.difference(DateTime(today.year, today.month, today.day)).inDays;
  }
}

class PlanItem {
  PlanItem.fromJson(Json j)
      : id = j['id'] as int,
        day = j['day'] as String,
        kind = j['kind'] as String,
        topicId = j['topic_id'] as String?,
        topic = j['topic'] as String?,
        subject = j['subject'] as String?,
        subjectId = j['subject_id'] as String?,
        minutes = j['minutes'] as int,
        done = j['done'] as bool;

  final int id;
  final String day;
  final String kind;
  final String? topicId;
  final String? topic;
  final String? subject;
  final String? subjectId;
  final int minutes;
  final bool done;

  String get title => switch (kind) {
        'study' => subject ?? 'Study',
        'revision' => 'Revision',
        'daily_test' => 'Daily practice test',
        'weekly_test' => 'Weekly test',
        'monthly_mock' => 'Monthly full mock',
        _ => kind,
      };

  String get detail => switch (kind) {
        'study' => topic ?? '',
        'revision' => 'Retest questions you got wrong',
        'daily_test' => '15 questions from today\'s topics and weak areas',
        'weekly_test' => '50 questions on this week\'s topics',
        'monthly_mock' => '100 questions in the Degree Prelims pattern',
        _ => '',
      };
}

class TopicStat {
  TopicStat.fromJson(Json j)
      : topicId = j['topic_id'] as String,
        topic = j['topic'] as String,
        subjectId = j['subject_id'] as String,
        subject = j['subject'] as String,
        weight = j['weight'] as int,
        bankSize = j['bank_size'] as int,
        attempts = j['attempts'] as int,
        accuracy = _pct(j['accuracy']);

  final String topicId;
  final String topic;
  final String subjectId;
  final String subject;
  final int weight;
  final int bankSize;
  final int attempts;
  final double? accuracy;
}

class SubjectStat {
  SubjectStat.fromJson(Json j)
      : subjectId = j['subject_id'] as String,
        subject = j['subject'] as String,
        weight = j['weight'] as int,
        attempts = j['attempts'] as int,
        accuracy = _pct(j['accuracy']),
        topicCount = j['topics'] is List ? (j['topics'] as List).length : j['topics'] as int,
        topicsStarted = j['topics_started'] as int,
        topics = j['topics'] is List
            ? (j['topics'] as List).map((t) => TopicStat.fromJson(t as Json)).toList()
            : const [];

  final String subjectId;
  final String subject;
  final int weight;
  final int attempts;
  final double? accuracy;
  final int topicCount;
  final int topicsStarted;
  final List<TopicStat> topics;
}

class ProgressSummary {
  ProgressSummary.fromJson(Json j)
      : attempts = j['attempts'] as int,
        accuracy = _pct(j['accuracy']),
        weekAttempts = j['week_attempts'] as int,
        weekAccuracy = _pct(j['week_accuracy']),
        testsTaken = j['tests_taken'] as int,
        streakDays = j['streak_days'] as int,
        revisionDue = j['revision_due'] as int,
        coverage = (j['syllabus_coverage'] as num).toDouble(),
        questionBank = j['question_bank'] as int,
        subjects = (j['subjects'] as List).map((s) => SubjectStat.fromJson(s as Json)).toList(),
        weakTopics = (j['weak_topics'] as List).map((t) => TopicStat.fromJson(t as Json)).toList();

  final int attempts;
  final double? accuracy;
  final int weekAttempts;
  final double? weekAccuracy;
  final int testsTaken;
  final int streakDays;
  final int revisionDue;
  final double coverage;
  final int questionBank;
  final List<SubjectStat> subjects;
  final List<TopicStat> weakTopics;
}

class Today {
  Today.fromJson(Json j)
      : date = j['date'] as String,
        plan = (j['plan'] as List).map((p) => PlanItem.fromJson(p as Json)).toList(),
        summary = ProgressSummary.fromJson(j['summary'] as Json),
        aiEnabled = j['ai_enabled'] as bool;

  final String date;
  final List<PlanItem> plan;
  final ProgressSummary summary;
  final bool aiEnabled;
}

class Question {
  Question.fromJson(Json j)
      : id = j['id'] as int,
        type = j['type'] as String,
        topicId = j['topic_id'] as String,
        topic = j['topic'] as String?,
        stem = j['stem'] as String,
        options = (j['options'] as List).cast<String>(),
        verification = j['verification'] as String,
        answerIndex = j['answer_index'] as int?,
        explanation = j['explanation'] as String?,
        selectedIndex = j['selected_index'] as int?;

  final int id;
  final String type;
  final String topicId;
  final String? topic;
  final String stem;
  final List<String> options;
  final String verification;
  final int? answerIndex;
  final String? explanation;
  final int? selectedIndex;

  String get sourceLabel => switch (type) {
        'verified_pyq' => verification == 'final_key' ? 'PYQ · final key' : 'PYQ · provisional key',
        'pyq_derived' => 'PYQ-style',
        'uploaded' => switch (verification) {
            'uploaded_key' => 'Your paper · your key',
            'ai_read_key' => 'Your paper · key read by AI',
            _ => 'Your paper · AI-answered',
          },
        _ => 'Mock',
      };
}

class TopicResult {
  TopicResult.fromJson(Json j)
      : topic = j['topic'] as String,
        correct = j['correct'] as int,
        wrong = j['wrong'] as int,
        skipped = j['skipped'] as int;

  final String topic;
  final int correct;
  final int wrong;
  final int skipped;
}

class TestInfo {
  TestInfo.fromJson(Json j)
      : id = j['id'] as int,
        type = j['type'] as String,
        title = j['title'] as String,
        questionCount = j['question_count'] as int,
        durationMinutes = j['duration_minutes'] as int,
        negativeMark = (j['negative_mark'] as num).toDouble(),
        createdAt = j['created_at'] as String,
        submittedAt = j['submitted_at'] as String?,
        score = _pct(j['score']),
        maxScore = _pct(j['max_score']),
        correct = j['correct'] as int?,
        wrong = j['wrong'] as int?,
        skipped = j['skipped'] as int?,
        questions = j['questions'] is List
            ? (j['questions'] as List).map((q) => Question.fromJson(q as Json)).toList()
            : const [],
        topics = j['topics'] is List
            ? (j['topics'] as List).map((t) => TopicResult.fromJson(t as Json)).toList()
            : const [];

  final int id;
  final String type;
  final String title;
  final int questionCount;
  final int durationMinutes;
  final double negativeMark;
  final String createdAt;
  final String? submittedAt;
  final double? score;
  final double? maxScore;
  final int? correct;
  final int? wrong;
  final int? skipped;
  final List<Question> questions;
  final List<TopicResult> topics;

  bool get submitted => submittedAt != null;
}

class PaperListing {
  PaperListing.fromJson(Json j)
      : raw = j,
        title = j['title'] as String,
        paperCode = j['paper_code'] as String?,
        medium = j['medium'] as String?,
        testDate = j['test_date'] as String?,
        keyType = j['key_type'] as String?,
        questionUrl = j['question_url'] as String?,
        keyUrl = j['key_url'] as String,
        paperId = j['paper_id'] as int?,
        status = j['status'] as String?;

  final Json raw;
  final String title;
  final String? paperCode;
  final String? medium;
  final String? testDate;
  final String? keyType;
  final String? questionUrl;
  final String keyUrl;
  final int? paperId;
  final String? status;
}

class Paper {
  Paper.fromJson(Json j)
      : id = j['id'] as int,
        title = j['title'] as String,
        paperCode = j['paper_code'] as String?,
        medium = j['medium'] as String?,
        testDate = j['test_date'] as String?,
        keyType = j['key_type'] as String?,
        keyUrl = j['key_url'] as String,
        source = j['source'] as String,
        level = j['level'] as String,
        answerSource = j['answer_source'] as String?,
        uploadedOn = j['uploaded_on'] as String?,
        attempts = j['attempts'] is List
            ? (j['attempts'] as List).map((t) => TestInfo.fromJson(t as Json)).toList()
            : const [],
        status = j['status'] as String,
        error = j['error'] as String?,
        questionCount = j['question_count'] as int;

  final int id;
  final String title;
  final String? paperCode;
  final String? medium;
  final String? testDate;
  final String? keyType;
  final String keyUrl;
  final String source;
  final String level;
  final String? answerSource;
  final String? uploadedOn;
  final List<TestInfo> attempts;
  final String status;
  final String? error;
  final int questionCount;

  bool get busy => status == 'queued' || status == 'downloading' || status == 'extracting';
  bool get uploaded => source == 'upload';

  String get answersLabel => switch (answerSource) {
        'official_key' => keyType ?? 'Official answer key',
        'uploaded_key' => 'Answers from your key',
        'ai_read_key' => 'Answers read from your key by AI',
        'ai_solved' => 'Answers worked out by AI. Check doubtful ones',
        _ => '',
      };
}

class ChatMessage {
  ChatMessage({required this.role, required this.content, this.testId});

  ChatMessage.fromJson(Json j)
      : role = j['role'] as String,
        content = j['content'] as String,
        testId = j['test_id'] as int?;

  final String role;
  final String content;
  final int? testId;
}

class ChatReply {
  ChatReply.fromJson(Json j)
      : reply = j['reply'] as String,
        tests = (j['tests'] as List).map((t) => TestInfo.fromJson(t as Json)).toList();

  final String reply;
  final List<TestInfo> tests;
}

class SectionReport {
  SectionReport.fromJson(Json j)
      : subjectId = j['subject_id'] as String,
        subject = j['subject'] as String,
        marks = j['marks'] as int,
        attempts = j['attempts'] as int,
        accuracy = _pct(j['accuracy']),
        status = j['status'] as String,
        weeklyMinutes = j['weekly_minutes'] as int,
        expectedMarks = _pct(j['expected_marks']),
        potentialGain = _pct(j['potential_gain']),
        weakTopics = (j['weak_topics'] as List).map((t) => TopicScore.fromJson(t as Json)).toList(),
        strongTopics = (j['strong_topics'] as List).map((t) => TopicScore.fromJson(t as Json)).toList();

  final String subjectId;
  final String subject;
  final int marks;
  final int attempts;
  final double? accuracy;
  final String status;
  final int weeklyMinutes;
  final double? expectedMarks;
  final double? potentialGain;
  final List<TopicScore> weakTopics;
  final List<TopicScore> strongTopics;

  String get statusLabel => switch (status) {
        'strong' => 'Strong',
        'average' => 'Average',
        'weak' => 'Weak',
        _ => 'Not assessed',
      };
}

class TopicScore {
  TopicScore.fromJson(Json j)
      : topicId = j['topic_id'] as String,
        topic = j['topic'] as String,
        accuracy = _pct(j['accuracy']);

  final String topicId;
  final String topic;
  final double? accuracy;
}

class StrengthReport {
  StrengthReport.fromJson(Json j)
      : assessed = j['assessed'] as bool,
        diagnostic = j['diagnostic'] == null ? null : (j['diagnostic'] as Json),
        dailyMinutes = j['daily_minutes'] as int,
        weeklyStudyMinutes = j['weekly_study_minutes'] as int,
        estimatedScore = _pct(j['estimated_score']),
        maxScore = j['max_score'] as int,
        sections = (j['sections'] as List).map((s) => SectionReport.fromJson(s as Json)).toList();

  final bool assessed;
  final Json? diagnostic;
  final int dailyMinutes;
  final int weeklyStudyMinutes;
  final double? estimatedScore;
  final int maxScore;
  final List<SectionReport> sections;
}

class SyncState {
  SyncState.fromJson(Json j)
      : running = j['running'] as bool,
        imported = j['imported'] as int,
        failed = j['failed'] as int,
        queued = j['queued'] as int,
        lastRun = j['last_run'] as String?;

  final bool running;
  final int imported;
  final int failed;
  final int queued;
  final String? lastRun;
}

class TopicVideo {
  TopicVideo.fromJson(Json j)
      : videoId = j['video_id'] as String,
        title = j['title'] as String,
        channel = j['channel'] as String,
        views = j['views'] as int,
        durationSeconds = j['duration_seconds'] as int,
        thumbnail = j['thumbnail'] as String?,
        url = j['url'] as String;

  final String videoId;
  final String title;
  final String channel;
  final int views;
  final int durationSeconds;
  final String? thumbnail;
  final String url;

  /// 1,234,567 -> "1.2M views"
  String get viewsLabel {
    if (views >= 1000000) return '${(views / 1000000).toStringAsFixed(1)}M views';
    if (views >= 1000) return '${(views / 1000).toStringAsFixed(views >= 100000 ? 0 : 1)}K views';
    return '$views views';
  }

  String get durationLabel {
    final h = durationSeconds ~/ 3600, m = (durationSeconds % 3600) ~/ 60, s = durationSeconds % 60;
    final mm = m.toString().padLeft(h > 0 ? 2 : 1, '0'), ss = s.toString().padLeft(2, '0');
    return h > 0 ? '$h:$mm:$ss' : '$mm:$ss';
  }
}
