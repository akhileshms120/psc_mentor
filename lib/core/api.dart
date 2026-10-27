import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart' show MediaType;
import 'package:shared_preferences/shared_preferences.dart';

import 'models.dart';

class ApiException implements Exception {
  ApiException(this.message, [this.status]);
  final String message;
  final int? status;

  @override
  String toString() => message;
}

/// A file picked for upload.
class UploadFile {
  UploadFile(this.name, this.bytes);
  final String name;
  final Uint8List bytes;

  String get contentType {
    final ext = name.split('.').last.toLowerCase();
    return switch (ext) {
      'pdf' => 'application/pdf',
      'png' => 'image/png',
      'webp' => 'image/webp',
      _ => 'image/jpeg',
    };
  }
}

/// Talks to the PSC Mentor backend. AI keys live on the server, never here.
class Api {
  Api._();
  static final Api instance = Api._();

  static const _urlKey = 'server_url';
  static const _tokenKey = 'auth_token';

  /// Bumped after anything that changes progress, so open screens reload.
  final ValueNotifier<int> changes = ValueNotifier(0);

  /// Whether a login token is stored. The app shows the login screen when false.
  final ValueNotifier<bool> signedIn = ValueNotifier(false);

  late String baseUrl;
  String? _token;
  http.Client client = http.Client();

  /// Built into release apps: `flutter build apk --dart-define=PSC_API_URL=https://NAME.onrender.com`
  /// The hosted server. Override for local development with
  /// `flutter run --dart-define=PSC_API_URL=http://localhost:8000`.
  static const hostedUrl = 'https://psc-mentor-api.onrender.com';
  static const _builtInUrl = String.fromEnvironment('PSC_API_URL', defaultValue: hostedUrl);

  static String get defaultUrl => _builtInUrl;

  Future<void> load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      baseUrl = prefs.getString(_urlKey) ?? defaultUrl;
      _token = prefs.getString(_tokenKey);
    } catch (_) {
      baseUrl = defaultUrl;
    }
    signedIn.value = _token != null;
  }

  /// For tests: start signed in (or out) without touching storage.
  void useToken(String? token) {
    _token = token;
    signedIn.value = token != null;
  }

  Future<void> setBaseUrl(String url) async {
    baseUrl = url.trim().replaceAll(RegExp(r'/+$'), '');
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_urlKey, baseUrl);
    changed();
  }

  Future<void> _saveToken(String? token) async {
    _token = token;
    signedIn.value = token != null;
    try {
      final prefs = await SharedPreferences.getInstance();
      if (token == null) {
        await prefs.remove(_tokenKey);
      } else {
        await prefs.setString(_tokenKey, token);
      }
    } catch (_) {}
  }

  void changed() => changes.value++;

  Map<String, String> get _authHeaders => {if (_token != null) 'authorization': 'Bearer $_token'};

  Future<dynamic> _send(String method, String path, [Object? body]) async {
    final uri = Uri.parse('$baseUrl$path');
    final headers = {'content-type': 'application/json', ..._authHeaders};
    late http.Response resp;
    try {
      final encoded = body == null ? null : jsonEncode(body);
      resp = await switch (method) {
        'POST' => client.post(uri, headers: headers, body: encoded),
        'PUT' => client.put(uri, headers: headers, body: encoded),
        _ => client.get(uri, headers: headers),
      }
          .timeout(const Duration(minutes: 3));
    } catch (_) {
      throw _unreachable();
    }
    return _decode(resp, path);
  }

  ApiException _unreachable() => ApiException(baseUrl.startsWith('https://')
      ? 'Cannot reach the PSC Mentor server at $baseUrl. A free server sleeps when unused and takes '
          'up to a minute to wake up, so try again shortly. Also check your internet connection.'
      : 'Cannot reach the PSC Mentor server at $baseUrl. '
          'Check that it is running and the address in settings is right.');

  dynamic _decode(http.Response resp, String path) {
    final text = utf8.decode(resp.bodyBytes);
    if (resp.statusCode >= 400) {
      String message = 'Server error ${resp.statusCode}';
      try {
        final detail = jsonDecode(text)['detail'];
        if (detail is String) message = detail;
      } catch (_) {}
      // An expired session sends the student back to the login screen.
      if (resp.statusCode == 401 && !path.startsWith('/auth/')) _saveToken(null);
      throw ApiException(message, resp.statusCode);
    }
    return jsonDecode(text);
  }

  // --- accounts -------------------------------------------------------------

  Future<User> signup({
    required String name,
    required String login,
    required String password,
    required int dailyMinutes,
    String? examDate,
    required String language,
  }) async {
    final data = await _send('POST', '/auth/signup', {
      'name': name,
      'login': login,
      'password': password,
      'daily_minutes': dailyMinutes,
      'exam_date': examDate,
      'language': language,
    });
    await _saveToken(data['token'] as String);
    return User.fromJson(data['user'] as Json);
  }

  Future<User> login(String login, String password) async {
    final data = await _send('POST', '/auth/login', {'login': login, 'password': password});
    await _saveToken(data['token'] as String);
    return User.fromJson(data['user'] as Json);
  }

  Future<void> logout() async {
    try {
      await _send('POST', '/auth/logout');
    } catch (_) {}
    await _saveToken(null);
  }

  Future<User> me() async => User.fromJson(await _send('GET', '/me'));

  /// Permanently deletes the account and all its data, then signs out.
  Future<void> deleteAccount(String password) async {
    await _send('POST', '/me/delete', {'password': password});
    await _saveToken(null);
  }

  Future<User> updateMe(Map<String, Object?> fields) async {
    final u = User.fromJson(await _send('PUT', '/me', fields));
    changed();
    return u;
  }

  Future<bool> health() async => (await _send('GET', '/health'))['ai_enabled'] as bool;

  // --- study ----------------------------------------------------------------

  Future<Today> today() async => Today.fromJson(await _send('GET', '/today'));

  Future<StrengthReport> analysis() async => StrengthReport.fromJson(await _send('GET', '/analysis'));

  Future<List<TopicVideo>> topicVideos(String topicId) async =>
      ((await _send('GET', '/topics/${Uri.encodeComponent(topicId)}/videos'))['videos'] as List)
          .map((v) => TopicVideo.fromJson(v as Json))
          .toList();

  Future<List<TextbookChapter>> topicTextbooks(String topicId) async =>
      (await _send('GET', '/topics/${Uri.encodeComponent(topicId)}/textbooks') as List)
          .map((c) => TextbookChapter.fromJson(c as Json))
          .toList();

  Future<List<NcertChapter>> ncertChapters() async =>
      (await _send('GET', '/textbooks/chapters') as List).map((c) => NcertChapter.fromJson(c as Json)).toList();

  Future<void> makeChapterQuestions(String chapterId) async {
    await _send('POST', '/textbooks/chapters/${Uri.encodeComponent(chapterId)}/generate');
    changed();
  }

  Future<Course> course() async => Course.fromJson(await _send('GET', '/course'));

  Future<List<PlanItem>> week() async =>
      (await _send('GET', '/plan/week') as List).map((p) => PlanItem.fromJson(p as Json)).toList();

  Future<void> regeneratePlan() async {
    await _send('POST', '/plan/regenerate');
    changed();
  }

  Future<void> togglePlanItem(int id) async {
    await _send('POST', '/plan/items/$id/toggle');
    changed();
  }

  Future<List<SubjectStat>> syllabus() async =>
      (await _send('GET', '/syllabus') as List).map((s) => SubjectStat.fromJson(s as Json)).toList();

  Future<ProgressSummary> summary() async => ProgressSummary.fromJson(await _send('GET', '/progress/summary'));

  // --- tests ----------------------------------------------------------------

  Future<TestInfo> createTest(String type, {String? topicId, int? paperId, String? chapterId}) async {
    final t = TestInfo.fromJson(await _send(
        'POST', '/tests', {'type': type, 'topic_id': topicId, 'paper_id': paperId, 'chapter_id': chapterId}));
    changed();
    return t;
  }

  Future<TestInfo> test(int id) async => TestInfo.fromJson(await _send('GET', '/tests/$id'));

  Future<List<TestInfo>> tests() async =>
      (await _send('GET', '/tests') as List).map((t) => TestInfo.fromJson(t as Json)).toList();

  Future<TestInfo> submit(int id, Map<int, int?> selected, Map<int, int> timeMs) async {
    final answers = [
      for (final e in selected.entries)
        {'question_id': e.key, 'selected': e.value, 'time_ms': timeMs[e.key]},
    ];
    final result = TestInfo.fromJson(await _send('POST', '/tests/$id/submit', {'answers': answers}));
    changed();
    return result;
  }

  Future<TestInfo> result(int id) async => TestInfo.fromJson(await _send('GET', '/tests/$id/result'));

  // --- papers ---------------------------------------------------------------

  Future<List<PaperListing>> pscPapers(int page) async =>
      (await _send('GET', '/psc/papers?page=$page') as List)
          .map((p) => PaperListing.fromJson(p as Json))
          .toList();

  Future<List<Paper>> papers() async =>
      (await _send('GET', '/papers') as List).map((p) => Paper.fromJson(p as Json)).toList();

  Future<Paper> paper(int id) async => Paper.fromJson(await _send('GET', '/papers/$id'));

  Future<List<ThrillerPost>> thrillerPapers() async =>
      (await _send('GET', '/thriller/papers') as List).map((p) => ThrillerPost.fromJson(p as Json)).toList();

  Future<Paper> importThriller(String url) async {
    final p = Paper.fromJson(await _send('POST', '/papers/import-thriller', {'url': url}));
    changed();
    return p;
  }

  Future<Paper> importPaper(PaperListing listing) async =>
      Paper.fromJson(await _send('POST', '/papers/import', listing.raw));

  Future<Paper> uploadPaper({
    required String title,
    required List<UploadFile> paper,
    List<UploadFile> key = const [],
    String booklet = 'A',
  }) async {
    final request = http.MultipartRequest('POST', Uri.parse('$baseUrl/papers/upload'))
      ..headers.addAll(_authHeaders)
      ..fields['title'] = title
      ..fields['booklet'] = booklet;
    for (final (field, files) in [('paper', paper), ('key', key)]) {
      for (final f in files) {
        request.files.add(http.MultipartFile.fromBytes(field, f.bytes,
            filename: f.name, contentType: MediaType.parse(f.contentType)));
      }
    }
    late http.Response resp;
    try {
      resp = await http.Response.fromStream(await client.send(request)).timeout(const Duration(minutes: 3));
    } catch (_) {
      throw _unreachable();
    }
    final p = Paper.fromJson(_decode(resp, '/papers/upload') as Json);
    changed();
    return p;
  }

  Future<SyncState> syncStatus() async => SyncState.fromJson(await _send('GET', '/papers/sync'));

  Future<SyncState> syncNow() async => SyncState.fromJson(await _send('POST', '/papers/sync'));

  // --- mentor ---------------------------------------------------------------

  Future<List<ChatMessage>> chatHistory() async =>
      (await _send('GET', '/mentor/history') as List).map((m) => ChatMessage.fromJson(m as Json)).toList();

  Future<ChatReply> chat(String text) async {
    final reply = ChatReply.fromJson(await _send('POST', '/mentor/chat', {'text': text}));
    changed();
    return reply;
  }
}
