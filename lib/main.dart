import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'data/word_repository.dart';
import 'models/word.dart';
import 'models/word_progress.dart';

void main() {
  runApp(const SwedishFlashcardsApp());
}

// ============================================================
// APP
// ============================================================

class SwedishFlashcardsApp extends StatelessWidget {
  const SwedishFlashcardsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Swedish Flashcards',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF006AA7),
        ),
        useMaterial3: true,
      ),
      home: const HomePage(),
    );
  }
}

// ============================================================
// SPACED REPETITION
// ============================================================

// Level:
// 0 = New
// 1 = Learning
// 2 = 1 day
// 3 = 3 days
// 4 = 7 days
// 5 = 14 days
// 6 = 30 days

const Map<int, int> reviewIntervals = {
  2: 1,
  3: 3,
  4: 7,
  5: 14,
  6: 30,
};

DateTime startOfDay(DateTime date) {
  return DateTime(
    date.year,
    date.month,
    date.day,
  );
}

bool isProgressDue(WordProgress progress) {
  if (progress.level < 2) {
    return false;
  }

  if (progress.nextReview == null) {
    return true;
  }

  final today = startOfDay(DateTime.now());
  final reviewDay = startOfDay(progress.nextReview!);

  return !reviewDay.isAfter(today);
}

// ============================================================
// STORAGE
// ============================================================

String progressKey(String wordId) {
  return 'progress_$wordId';
}

String oldStatusKey(String wordId) {
  return 'status_$wordId';
}

Future<Map<String, WordProgress>> loadProgress(
  List<Word> words,
) async {
  final prefs = await SharedPreferences.getInstance();

  final Map<String, WordProgress> result = {};

  for (final word in words) {
    final saved = prefs.getString(
      progressKey(word.id),
    );

    // --------------------------------------------------------
    // NEW FORMAT
    // --------------------------------------------------------

    if (saved != null) {
      try {
        final Map<String, dynamic> data =
            jsonDecode(saved);

        final level = data['level'] as int? ?? 0;

        final nextReviewString =
            data['nextReview'] as String?;

        DateTime? nextReview;

        if (nextReviewString != null) {
          nextReview =
              DateTime.tryParse(nextReviewString);
        }

        if (level > 0) {
          result[word.id] = WordProgress(
            level: level,
            nextReview: nextReview,
          );
        }

        continue;
      } catch (_) {
        // If stored data is corrupted,
        // try the old format below.
      }
    }

    // --------------------------------------------------------
    // MIGRATE OLD FORMAT
    // --------------------------------------------------------

    final oldStatus = prefs.getString(
      oldStatusKey(word.id),
    );

    if (oldStatus == 'learning') {
      const migratedProgress = WordProgress(
        level: 1,
      );

      result[word.id] = migratedProgress;

      await saveProgress(
        word,
        migratedProgress,
      );
    } else if (oldStatus == 'known') {
      final tomorrow = startOfDay(
        DateTime.now().add(
          const Duration(days: 1),
        ),
      );

      final migratedProgress = WordProgress(
        level: 2,
        nextReview: tomorrow,
      );

      result[word.id] = migratedProgress;

      await saveProgress(
        word,
        migratedProgress,
      );
    }
  }

  return result;
}

Future<void> saveProgress(
  Word word,
  WordProgress progress,
) async {
  final prefs = await SharedPreferences.getInstance();

  final data = {
    'level': progress.level,
    'nextReview':
        progress.nextReview?.toIso8601String(),
  };

  await prefs.setString(
    progressKey(word.id),
    jsonEncode(data),
  );
}

Future<void> resetAllProgress() async {
  final prefs = await SharedPreferences.getInstance();

  final keys = prefs.getKeys().toList();

  for (final key in keys) {
    if (key.startsWith('progress_') ||
        key.startsWith('status_')) {
      await prefs.remove(key);
    }
  }
}

// ============================================================
// ANSWER LOGIC
// ============================================================

Future<WordProgress> markLearning(
  Word word,
) async {
  const progress = WordProgress(
    level: 1,
    nextReview: null,
  );

  await saveProgress(
    word,
    progress,
  );

  return progress;
}

Future<WordProgress> markKnown(
  Word word,
  WordProgress? currentProgress,
) async {
  final currentLevel =
      currentProgress?.level ?? 0;

  int nextLevel;

  if (currentLevel <= 1) {
    nextLevel = 2;
  } else {
    nextLevel = min(
      currentLevel + 1,
      6,
    );
  }

  final days = reviewIntervals[nextLevel] ?? 30;

  final nextReview = startOfDay(
    DateTime.now().add(
      Duration(days: days),
    ),
  );

  final progress = WordProgress(
    level: nextLevel,
    nextReview: nextReview,
  );

  await saveProgress(
    word,
    progress,
  );

  return progress;
}

// ============================================================
// SESSION BUILDERS
// ============================================================

List<Word> buildStudySession({
  required List<Word> sourceWords,
  required Map<String, WordProgress> progress,
  required int? sessionSize,
}) {
  final random = Random();

  final dueWords = <Word>[];
  final learningWords = <Word>[];
  final newWords = <Word>[];

  for (final word in sourceWords) {
    final wordProgress = progress[word.id];

    if (wordProgress == null ||
        wordProgress.level == 0) {
      newWords.add(word);
      continue;
    }

    if (wordProgress.level == 1) {
      learningWords.add(word);
      continue;
    }

    if (isProgressDue(wordProgress)) {
      dueWords.add(word);
    }
  }

  dueWords.shuffle(random);
  learningWords.shuffle(random);
  newWords.shuffle(random);

  final candidates = [
    ...dueWords,
    ...learningWords,
    ...newWords,
  ];

  if (sessionSize == null) {
    return candidates;
  }

  return candidates.take(sessionSize).toList();
}

List<Word> buildDailyReviewSession({
  required List<Word> sourceWords,
  required Map<String, WordProgress> progress,
}) {
  final random = Random();

  final dueWords = sourceWords.where((word) {
    final wordProgress = progress[word.id];

    return wordProgress != null &&
        wordProgress.level >= 2 &&
        isProgressDue(wordProgress);
  }).toList();

  dueWords.shuffle(random);

  return dueWords;
}

// ============================================================
// HOME PAGE
// ============================================================

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() =>
      _HomePageState();
}

class _HomePageState extends State<HomePage> {
  List<Word> allWords = [];

  Map<String, WordProgress> progress = {};

  bool isLoading = true;

  String? errorMessage;

  @override
  void initState() {
    super.initState();
    loadAppData();
  }

  // ----------------------------------------------------------
  // LOAD
  // ----------------------------------------------------------

  Future<void> loadAppData() async {
    try {
      final words =
          await WordRepository.loadWords();

      final loadedProgress =
          await loadProgress(words);

      if (!mounted) return;

      setState(() {
        allWords = words;
        progress = loadedProgress;
        isLoading = false;
        errorMessage = null;
      });
    } catch (error) {
      if (!mounted) return;

      setState(() {
        isLoading = false;
        errorMessage = error.toString();
      });
    }
  }

  Future<void> refreshProgress() async {
    final loadedProgress =
        await loadProgress(allWords);

    if (!mounted) return;

    setState(() {
      progress = loadedProgress;
    });
  }

  // ----------------------------------------------------------
  // COUNTERS
  // ----------------------------------------------------------

  int get newCount {
    return allWords.where((word) {
      final p = progress[word.id];

      return p == null || p.level == 0;
    }).length;
  }

  int get learningCount {
    return allWords.where((word) {
      return progress[word.id]?.level == 1;
    }).length;
  }

  int get dueCount {
    return allWords.where((word) {
      final p = progress[word.id];

      return p != null &&
          p.level >= 2 &&
          isProgressDue(p);
    }).length;
  }

  int get learnedCount {
    return allWords.where((word) {
      final p = progress[word.id];

      return p != null && p.level >= 2;
    }).length;
  }

  // ----------------------------------------------------------
  // NAVIGATION
  // ----------------------------------------------------------

  Future<void> openStudyOptions({
    required String title,
    required List<Word> words,
  }) async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) =>
            StudyOptionsPage(
          title: title,
          words: words,
          progress: progress,
        ),
      ),
    );

    await refreshProgress();
  }

  Future<void> openChapterSelection() async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) =>
            ChapterSelectionPage(
          allWords: allWords,
          progress: progress,
        ),
      ),
    );

    await refreshProgress();
  }

  Future<void> openSettings() async {
    final wasReset = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (context) =>
            const SettingsPage(),
      ),
    );

    if (wasReset == true) {
      await refreshProgress();
    }
  }

  // ----------------------------------------------------------
  // DAILY REVIEW
  // ----------------------------------------------------------

  Future<void> startDailyReview() async {
    final reviewWords =
        buildDailyReviewSession(
      sourceWords: allWords,
      progress: progress,
    );

    if (reviewWords.isEmpty) {
      if (!mounted) return;

      ScaffoldMessenger.of(context)
          .showSnackBar(
        const SnackBar(
          content: Text(
            'No reviews are due right now.',
          ),
        ),
      );

      return;
    }

    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) =>
            FlashcardPage(
          words: reviewWords,
          title: 'Daily Review',
          progress: progress,
        ),
      ),
    );

    await refreshProgress();
  }

  // ----------------------------------------------------------
  // BUILD
  // ----------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    if (isLoading) {
      return const Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 20),
              Text(
                'Loading vocabulary...',
                style: TextStyle(
                  fontSize: 18,
                ),
              ),
            ],
          ),
        ),
      );
    }

    if (errorMessage != null) {
      return Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(30),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  Icons.error_outline,
                  size: 60,
                  color: Colors.red,
                ),
                const SizedBox(height: 20),
                const Text(
                  'Could not load vocabulary',
                  style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  errorMessage!,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 25),
                FilledButton(
                  onPressed: () {
                    setState(() {
                      isLoading = true;
                      errorMessage = null;
                    });

                    loadAppData();
                  },
                  child:
                      const Text('TRY AGAIN'),
                ),
              ],
            ),
          ),
        ),
      );
    }

    final completion = allWords.isEmpty
        ? 0.0
        : learnedCount / allWords.length;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding:
                const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints:
                  const BoxConstraints(
                maxWidth: 550,
              ),
              child: Column(
                children: [
                  // HEADER

                  const Text(
                    '🇸🇪',
                    style:
                        TextStyle(fontSize: 55),
                  ),

                  const SizedBox(height: 10),

                  const Text(
                    'Swedish Flashcards',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 30,
                      fontWeight:
                          FontWeight.bold,
                    ),
                  ),

                  const SizedBox(height: 8),

                  Text(
                    '${allWords.length} words in your collection',
                    style: const TextStyle(
                      color: Colors.grey,
                    ),
                  ),

                  const SizedBox(height: 35),

                  // PROGRESS

                  const SectionTitle(
                    title: 'YOUR PROGRESS',
                  ),

                  const SizedBox(height: 12),

                  ProgressSummaryTile(
                    icon:
                        Icons.fiber_new_outlined,
                    title: 'New',
                    count: newCount,
                  ),

                  ProgressSummaryTile(
                    icon: Icons.school_outlined,
                    title: 'Learning',
                    count: learningCount,
                  ),

                  ProgressSummaryTile(
                    icon:
                        Icons.schedule_outlined,
                    title: 'Due for review',
                    count: dueCount,
                  ),

                  ProgressSummaryTile(
                    icon: Icons
                        .check_circle_outline,
                    title: 'Learned',
                    count: learnedCount,
                  ),

                  const SizedBox(height: 20),

                  LinearProgressIndicator(
                    value: completion,
                    minHeight: 10,
                    borderRadius:
                        BorderRadius.circular(10),
                  ),

                  const SizedBox(height: 10),

                  Text(
                    '$learnedCount of ${allWords.length} words entered the review system',
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: Colors.grey,
                    ),
                  ),

                  const SizedBox(height: 40),

                  // TODAY

                  const SectionTitle(
                    title: 'TODAY',
                  ),

                  const SizedBox(height: 12),

                  if (dueCount > 0)
                    DailyReviewTile(
                      dueCount: dueCount,
                      onTap: startDailyReview,
                    )
                  else
                    const DailyCompleteTile(),

                  const SizedBox(height: 40),

                  // MATERIAL

                  const SectionTitle(
                    title: 'CHOOSE MATERIAL',
                  ),

                  const SizedBox(height: 12),

                  MaterialTile(
                    icon: Icons
                        .library_books_outlined,
                    title: 'All Words',
                    subtitle:
                        'Entire vocabulary collection',
                    onTap: () {
                      openStudyOptions(
                        title: 'All Words',
                        words: allWords,
                      );
                    },
                  ),

                  const SizedBox(height: 12),

                  MaterialTile(
                    icon:
                        Icons.menu_book_outlined,
                    title: 'By Chapter',
                    subtitle:
                        'Choose Kapitel 1–20',
                    onTap:
                        openChapterSelection,
                  ),

                  const SizedBox(height: 40),

                  // SETTINGS

                  const SectionTitle(
                    title: 'SETTINGS',
                  ),

                  const SizedBox(height: 12),

                  MaterialTile(
                    icon: Icons.settings_outlined,
                    title: 'Settings',
                    subtitle:
                        'Manage your learning data',
                    onTap: openSettings,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ============================================================
// SETTINGS
// ============================================================

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() =>
      _SettingsPageState();
}

class _SettingsPageState
    extends State<SettingsPage> {
  bool isResetting = false;

  Future<void> confirmReset() async {
    final firstConfirmation =
        await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text(
            'Reset all progress?',
          ),
          content: const Text(
            'This will remove all learning progress, '
            'review levels and scheduled reviews.\n\n'
            'Your vocabulary database will not be deleted.',
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(
                  dialogContext,
                  false,
                );
              },
              child: const Text('CANCEL'),
            ),
            FilledButton(
              onPressed: () {
                Navigator.pop(
                  dialogContext,
                  true,
                );
              },
              child: const Text('CONTINUE'),
            ),
          ],
        );
      },
    );

    if (firstConfirmation != true ||
        !mounted) {
      return;
    }

    final finalConfirmation =
        await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          icon: const Icon(
            Icons.warning_amber_rounded,
            size: 45,
          ),
          title: const Text(
            'Are you absolutely sure?',
          ),
          content: const Text(
            'This action cannot be undone. '
            'All words will return to New.',
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(
                  dialogContext,
                  false,
                );
              },
              child: const Text('CANCEL'),
            ),
            FilledButton(
              onPressed: () {
                Navigator.pop(
                  dialogContext,
                  true,
                );
              },
              child:
                  const Text('RESET'),
            ),
          ],
        );
      },
    );

    if (finalConfirmation != true ||
        !mounted) {
      return;
    }

    setState(() {
      isResetting = true;
    });

    await resetAllProgress();

    if (!mounted) return;

    setState(() {
      isResetting = false;
    });

    ScaffoldMessenger.of(context)
        .showSnackBar(
      const SnackBar(
        content: Text(
          'Learning progress has been reset.',
        ),
      ),
    );

    Navigator.pop(context, true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding:
                const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints:
                  const BoxConstraints(
                maxWidth: 550,
              ),
              child: Column(
                crossAxisAlignment:
                    CrossAxisAlignment.stretch,
                children: [
                  const Icon(
                    Icons.settings_outlined,
                    size: 65,
                  ),

                  const SizedBox(height: 15),

                  const Text(
                    'Settings',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 30,
                      fontWeight:
                          FontWeight.bold,
                    ),
                  ),

                  const SizedBox(height: 40),

                  const SectionTitle(
                    title: 'LEARNING DATA',
                  ),

                  const SizedBox(height: 12),

                  Card(
                    child: Padding(
                      padding:
                          const EdgeInsets.all(
                        20,
                      ),
                      child: Column(
                        crossAxisAlignment:
                            CrossAxisAlignment
                                .start,
                        children: [
                          const Row(
                            children: [
                              Icon(
                                Icons
                                    .restart_alt,
                                size: 30,
                              ),
                              SizedBox(width: 12),
                              Expanded(
                                child: Text(
                                  'Reset Progress',
                                  style:
                                      TextStyle(
                                    fontSize: 18,
                                    fontWeight:
                                        FontWeight
                                            .bold,
                                  ),
                                ),
                              ),
                            ],
                          ),

                          const SizedBox(
                            height: 12,
                          ),

                          const Text(
                            'Return all flashcards to New '
                            'and remove all scheduled reviews.',
                            style: TextStyle(
                              color: Colors.grey,
                            ),
                          ),

                          const SizedBox(
                            height: 20,
                          ),

                          SizedBox(
                            width:
                                double.infinity,
                            child:
                                OutlinedButton
                                    .icon(
                              onPressed:
                                  isResetting
                                      ? null
                                      : confirmReset,
                              icon: isResetting
                                  ? const SizedBox(
                                      width: 18,
                                      height: 18,
                                      child:
                                          CircularProgressIndicator(
                                        strokeWidth:
                                            2,
                                      ),
                                    )
                                  : const Icon(
                                      Icons
                                          .delete_outline,
                                    ),
                              label: Text(
                                isResetting
                                    ? 'RESETTING...'
                                    : 'RESET ALL PROGRESS',
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),

                  const SizedBox(height: 25),

                  const Text(
                    'Resetting progress does not modify '
                    'the vocabulary database.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.grey,
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ============================================================
// CHAPTER SELECTION
// ============================================================

class ChapterSelectionPage
    extends StatefulWidget {
  final List<Word> allWords;
  final Map<String, WordProgress> progress;

  const ChapterSelectionPage({
    super.key,
    required this.allWords,
    required this.progress,
  });

  @override
  State<ChapterSelectionPage> createState() =>
      _ChapterSelectionPageState();
}

class _ChapterSelectionPageState
    extends State<ChapterSelectionPage> {
  late Map<String, WordProgress> progress;

  @override
  void initState() {
    super.initState();

    progress =
        Map<String, WordProgress>.from(
      widget.progress,
    );
  }

  Future<void> refreshProgress() async {
    final loaded =
        await loadProgress(widget.allWords);

    if (!mounted) return;

    setState(() {
      progress = loaded;
    });
  }

  Future<void> openChapter(
    int chapter,
    List<Word> words,
  ) async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) =>
            StudyOptionsPage(
          title: 'Kapitel $chapter',
          words: words,
          progress: progress,
        ),
      ),
    );

    await refreshProgress();
  }

  @override
  Widget build(BuildContext context) {
    final chapters = widget.allWords
        .map((word) => word.chapter)
        .where((chapter) => chapter > 0)
        .toSet()
        .toList()
      ..sort();

    return Scaffold(
      appBar: AppBar(
        title: const Text('By Chapter'),
      ),
      body: SafeArea(
        child: Center(
          child: ListView(
            padding:
                const EdgeInsets.all(24),
            children: [
              Center(
                child: ConstrainedBox(
                  constraints:
                      const BoxConstraints(
                    maxWidth: 550,
                  ),
                  child: Column(
                    children: [
                      const Icon(
                        Icons
                            .menu_book_outlined,
                        size: 60,
                      ),
                      const SizedBox(
                        height: 15,
                      ),
                      const Text(
                        'Choose a chapter',
                        style: TextStyle(
                          fontSize: 28,
                          fontWeight:
                              FontWeight.bold,
                        ),
                      ),
                      const SizedBox(
                        height: 30,
                      ),

                      ...chapters.map(
                        (chapter) {
                          final words = widget
                              .allWords
                              .where(
                                (word) =>
                                    word.chapter ==
                                    chapter,
                              )
                              .toList();

                          final learned =
                              words.where(
                            (word) {
                              final p =
                                  progress[
                                      word.id];

                              return p !=
                                      null &&
                                  p.level >= 2;
                            },
                          ).length;

                          return Padding(
                            padding:
                                const EdgeInsets
                                    .only(
                              bottom: 10,
                            ),
                            child:
                                MaterialTile(
                              icon: Icons
                                  .menu_book_outlined,
                              title:
                                  'Kapitel $chapter',
                              subtitle:
                                  '${words.length} words • $learned learned',
                              onTap: () {
                                openChapter(
                                  chapter,
                                  words,
                                );
                              },
                            ),
                          );
                        },
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ============================================================
// STUDY OPTIONS
// ============================================================

class StudyOptionsPage
    extends StatefulWidget {
  final String title;
  final List<Word> words;
  final Map<String, WordProgress> progress;

  const StudyOptionsPage({
    super.key,
    required this.title,
    required this.words,
    required this.progress,
  });

  @override
  State<StudyOptionsPage> createState() =>
      _StudyOptionsPageState();
}

class _StudyOptionsPageState
    extends State<StudyOptionsPage> {
  late Map<String, WordProgress> progress;

  @override
  void initState() {
    super.initState();

    progress =
        Map<String, WordProgress>.from(
      widget.progress,
    );
  }

  int get newCount {
    return widget.words.where((word) {
      final p = progress[word.id];

      return p == null || p.level == 0;
    }).length;
  }

  int get learningCount {
    return widget.words.where((word) {
      return progress[word.id]?.level == 1;
    }).length;
  }

  int get dueCount {
    return widget.words.where((word) {
      final p = progress[word.id];

      return p != null &&
          p.level >= 2 &&
          isProgressDue(p);
    }).length;
  }

  int get learnedCount {
    return widget.words.where((word) {
      final p = progress[word.id];

      return p != null && p.level >= 2;
    }).length;
  }

  int get availableCount {
    return newCount +
        learningCount +
        dueCount;
  }

  Future<void> refreshProgress() async {
    final loaded =
        await loadProgress(widget.words);

    if (!mounted) return;

    setState(() {
      for (final word in widget.words) {
        progress.remove(word.id);
      }

      progress.addAll(loaded);
    });
  }

  Future<void> startSession(
    int? size,
  ) async {
    final session = buildStudySession(
      sourceWords: widget.words,
      progress: progress,
      sessionSize: size,
    );

    if (session.isEmpty) {
      if (!mounted) return;

      ScaffoldMessenger.of(context)
          .showSnackBar(
        const SnackBar(
          content: Text(
            'Nothing is due right now. Great job!',
          ),
        ),
      );

      return;
    }

    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) =>
            FlashcardPage(
          words: session,
          title: widget.title,
          progress: progress,
        ),
      ),
    );

    await refreshProgress();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.title),
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding:
                const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints:
                  const BoxConstraints(
                maxWidth: 550,
              ),
              child: Column(
                children: [
                  const Icon(
                    Icons.school_outlined,
                    size: 65,
                  ),

                  const SizedBox(height: 15),

                  Text(
                    widget.title,
                    style: const TextStyle(
                      fontSize: 30,
                      fontWeight:
                          FontWeight.bold,
                    ),
                  ),

                  const SizedBox(height: 8),

                  Text(
                    '${widget.words.length} words',
                    style: const TextStyle(
                      color: Colors.grey,
                    ),
                  ),

                  const SizedBox(height: 30),

                  const SectionTitle(
                    title: 'PROGRESS',
                  ),

                  const SizedBox(height: 12),

                  ProgressSummaryTile(
                    icon:
                        Icons.fiber_new_outlined,
                    title: 'New',
                    count: newCount,
                  ),

                  ProgressSummaryTile(
                    icon: Icons.school_outlined,
                    title: 'Learning',
                    count: learningCount,
                  ),

                  ProgressSummaryTile(
                    icon:
                        Icons.schedule_outlined,
                    title: 'Due',
                    count: dueCount,
                  ),

                  ProgressSummaryTile(
                    icon: Icons
                        .check_circle_outline,
                    title: 'Learned',
                    count: learnedCount,
                  ),

                  const SizedBox(height: 35),

                  const SectionTitle(
                    title: 'CHOOSE SESSION',
                  ),

                  const SizedBox(height: 12),

                  SessionTile(
                    icon: Icons.bolt,
                    title: 'Quick Session',
                    subtitle: '10 words',
                    onTap: () {
                      startSession(10);
                    },
                  ),

                  const SizedBox(height: 10),

                  SessionTile(
                    icon: Icons.school_outlined,
                    title: 'Standard Session',
                    subtitle:
                        '20 words • Recommended',
                    recommended: true,
                    onTap: () {
                      startSession(20);
                    },
                  ),

                  const SizedBox(height: 10),

                  SessionTile(
                    icon: Icons
                        .local_fire_department_outlined,
                    title: 'Long Session',
                    subtitle: '50 words',
                    onTap: () {
                      startSession(50);
                    },
                  ),

                  const SizedBox(height: 10),

                  SessionTile(
                    icon: Icons.all_inclusive,
                    title: 'Study All',
                    subtitle:
                        '$availableCount words currently available',
                    onTap: () {
                      startSession(null);
                    },
                  ),

                  const SizedBox(height: 25),

                  const Text(
                    'Due reviews are shown first, followed by '
                    'Learning words and then new vocabulary.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.grey,
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ============================================================
// FLASHCARDS
// ============================================================

class FlashcardPage extends StatefulWidget {
  final List<Word> words;
  final String title;
  final Map<String, WordProgress> progress;

  const FlashcardPage({
    super.key,
    required this.words,
    required this.title,
    required this.progress,
  });

  @override
  State<FlashcardPage> createState() =>
      _FlashcardPageState();
}

class _FlashcardPageState
    extends State<FlashcardPage> {
  int currentIndex = 0;

  bool showTranslation = false;

  int sessionKnown = 0;
  int sessionLearning = 0;

  late Map<String, WordProgress> progress;

  @override
  void initState() {
    super.initState();

    progress =
        Map<String, WordProgress>.from(
      widget.progress,
    );
  }

  Word get currentWord =>
      widget.words[currentIndex];

  Future<void> answerLearning() async {
    final newProgress =
        await markLearning(currentWord);

    progress[currentWord.id] =
        newProgress;

    sessionLearning++;

    await nextWord();
  }

  Future<void> answerKnown() async {
    final newProgress = await markKnown(
      currentWord,
      progress[currentWord.id],
    );

    progress[currentWord.id] =
        newProgress;

    sessionKnown++;

    await nextWord();
  }

  Future<void> nextWord() async {
    if (currentIndex <
        widget.words.length - 1) {
      if (!mounted) return;

      setState(() {
        currentIndex++;
        showTranslation = false;
      });

      return;
    }

    if (!mounted) return;

    await showDialog(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text(
            'Session complete! 🎉',
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'You reviewed ${widget.words.length} words.',
              ),
              const SizedBox(height: 20),
              Row(
                mainAxisAlignment:
                    MainAxisAlignment
                        .spaceAround,
                children: [
                  Column(
                    children: [
                      Text(
                        '$sessionLearning',
                        style:
                            const TextStyle(
                          fontSize: 26,
                          fontWeight:
                              FontWeight.bold,
                        ),
                      ),
                      const Text('Learning'),
                    ],
                  ),
                  Column(
                    children: [
                      Text(
                        '$sessionKnown',
                        style:
                            const TextStyle(
                          fontSize: 26,
                          fontWeight:
                              FontWeight.bold,
                        ),
                      ),
                      const Text('I knew it'),
                    ],
                  ),
                ],
              ),
            ],
          ),
          actions: [
            FilledButton(
              onPressed: () {
                Navigator.pop(
                  dialogContext,
                );

                Navigator.pop(context);
              },
              child: const Text('DONE'),
            ),
          ],
        );
      },
    );
  }

  String currentStatusText() {
    final p = progress[currentWord.id];

    if (p == null || p.level == 0) {
      return 'NEW';
    }

    if (p.level == 1) {
      return 'LEARNING';
    }

    if (isProgressDue(p)) {
      return 'REVIEW';
    }

    return 'LEVEL ${p.level}';
  }

  @override
  Widget build(BuildContext context) {
    final cardProgress =
        (currentIndex + 1) /
            widget.words.length;

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.title),
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding:
                const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints:
                  const BoxConstraints(
                maxWidth: 600,
              ),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment:
                        MainAxisAlignment
                            .spaceBetween,
                    children: [
                      Text(
                        '${currentIndex + 1} / ${widget.words.length}',
                        style:
                            const TextStyle(
                          fontWeight:
                              FontWeight.bold,
                        ),
                      ),
                      Text(
                        currentStatusText(),
                        style:
                            const TextStyle(
                          color: Colors.grey,
                          fontWeight:
                              FontWeight.bold,
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: 10),

                  LinearProgressIndicator(
                    value: cardProgress,
                    minHeight: 8,
                    borderRadius:
                        BorderRadius.circular(
                      10,
                    ),
                  ),

                  const SizedBox(height: 30),

                  GestureDetector(
                    onTap: () {
                      setState(() {
                        showTranslation =
                            !showTranslation;
                      });
                    },
                    child: Card(
                      elevation: 4,
                      child: SizedBox(
                        width: double.infinity,
                        height: 380,
                        child: Padding(
                          padding:
                              const EdgeInsets
                                  .all(30),
                          child: Column(
                            mainAxisAlignment:
                                MainAxisAlignment
                                    .center,
                            children: [
                              Text(
                                showTranslation
                                    ? 'ENGLISH'
                                    : 'SVENSKA',
                                style:
                                    const TextStyle(
                                  fontSize: 14,
                                  fontWeight:
                                      FontWeight
                                          .bold,
                                  color:
                                      Colors.grey,
                                ),
                              ),

                              const SizedBox(
                                height: 30,
                              ),

                              if (!showTranslation)
                                ...[
                                  Text(
                                    currentWord
                                        .swedish,
                                    textAlign:
                                        TextAlign
                                            .center,
                                    style:
                                        const TextStyle(
                                      fontSize: 42,
                                      fontWeight:
                                          FontWeight
                                              .bold,
                                    ),
                                  ),

                                  if (currentWord
                                      .forms
                                      .isNotEmpty) ...[
                                    const SizedBox(
                                      height: 15,
                                    ),
                                    Text(
                                      currentWord
                                          .forms,
                                      textAlign:
                                          TextAlign
                                              .center,
                                      style:
                                          const TextStyle(
                                        fontSize: 19,
                                        color: Colors
                                            .grey,
                                      ),
                                    ),
                                  ],
                                ]
                              else ...[
                                Text(
                                  currentWord
                                      .english,
                                  textAlign:
                                      TextAlign
                                          .center,
                                  style:
                                      const TextStyle(
                                    fontSize: 38,
                                    fontWeight:
                                        FontWeight
                                            .bold,
                                  ),
                                ),

                                const SizedBox(
                                  height: 25,
                                ),

                                Text(
                                  currentWord
                                      .swedish,
                                  textAlign:
                                      TextAlign
                                          .center,
                                  style:
                                      const TextStyle(
                                    fontSize: 22,
                                    fontWeight:
                                        FontWeight
                                            .w600,
                                  ),
                                ),

                                if (currentWord
                                    .forms
                                    .isNotEmpty) ...[
                                  const SizedBox(
                                    height: 8,
                                  ),
                                  Text(
                                    currentWord
                                        .forms,
                                    textAlign:
                                        TextAlign
                                            .center,
                                    style:
                                        const TextStyle(
                                      fontSize: 17,
                                      color: Colors
                                          .grey,
                                    ),
                                  ),
                                ],
                              ],

                              const SizedBox(
                                height: 35,
                              ),

                              Text(
                                showTranslation
                                    ? 'How well did you know it?'
                                    : 'Tap to reveal',
                                style:
                                    const TextStyle(
                                  color:
                                      Colors.grey,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),

                  const SizedBox(height: 25),

                  if (showTranslation)
                    Row(
                      children: [
                        Expanded(
                          child:
                              OutlinedButton
                                  .icon(
                            onPressed:
                                answerLearning,
                            icon:
                                const Icon(
                              Icons.close,
                            ),
                            label:
                                const Text(
                              'LEARNING',
                            ),
                            style:
                                OutlinedButton
                                    .styleFrom(
                              minimumSize:
                                  const Size
                                      .fromHeight(
                                55,
                              ),
                            ),
                          ),
                        ),

                        const SizedBox(
                          width: 15,
                        ),

                        Expanded(
                          child:
                              FilledButton
                                  .icon(
                            onPressed:
                                answerKnown,
                            icon:
                                const Icon(
                              Icons.check,
                            ),
                            label:
                                const Text(
                              'I KNOW',
                            ),
                            style:
                                FilledButton
                                    .styleFrom(
                              minimumSize:
                                  const Size
                                      .fromHeight(
                                55,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ============================================================
// UI COMPONENTS
// ============================================================

class SectionTitle extends StatelessWidget {
  final String title;

  const SectionTitle({
    super.key,
    required this.title,
  });

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Text(
        title,
        style: const TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.bold,
          color: Colors.grey,
        ),
      ),
    );
  }
}

class ProgressSummaryTile
    extends StatelessWidget {
  final IconData icon;
  final String title;
  final int count;

  const ProgressSummaryTile({
    super.key,
    required this.icon,
    required this.title,
    required this.count,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin:
          const EdgeInsets.only(bottom: 10),
      child: ListTile(
        leading: Icon(
          icon,
          size: 30,
        ),
        title: Text(
          title,
          style: const TextStyle(
            fontWeight: FontWeight.w600,
          ),
        ),
        trailing: Text(
          count.toString(),
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
    );
  }
}

class MaterialTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const MaterialTile({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: ListTile(
        onTap: onTap,
        leading: Icon(
          icon,
          size: 30,
        ),
        title: Text(
          title,
          style: const TextStyle(
            fontWeight: FontWeight.w600,
          ),
        ),
        subtitle: Text(subtitle),
        trailing:
            const Icon(Icons.chevron_right),
      ),
    );
  }
}

class SessionTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final bool recommended;

  const SessionTile({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.recommended = false,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: ListTile(
        onTap: onTap,
        leading: Icon(
          icon,
          size: 30,
        ),
        title: Row(
          children: [
            Flexible(
              child: Text(
                title,
                style: const TextStyle(
                  fontWeight:
                      FontWeight.w600,
                ),
              ),
            ),
            if (recommended) ...[
              const SizedBox(width: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(
                  horizontal: 8,
                  vertical: 3,
                ),
                decoration: BoxDecoration(
                  color: Theme.of(context)
                      .colorScheme
                      .primaryContainer,
                  borderRadius:
                      BorderRadius.circular(20),
                ),
                child: const Text(
                  'RECOMMENDED',
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight:
                        FontWeight.bold,
                  ),
                ),
              ),
            ],
          ],
        ),
        subtitle: Text(subtitle),
        trailing:
            const Icon(Icons.chevron_right),
      ),
    );
  }
}

class DailyReviewTile extends StatelessWidget {
  final int dueCount;
  final VoidCallback onTap;

  const DailyReviewTile({
    super.key,
    required this.dueCount,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: InkWell(
        onTap: onTap,
        borderRadius:
            BorderRadius.circular(12),
        child: Padding(
          padding:
              const EdgeInsets.all(20),
          child: Row(
            children: [
              Container(
                width: 55,
                height: 55,
                decoration: BoxDecoration(
                  color: Theme.of(context)
                      .colorScheme
                      .primaryContainer,
                  borderRadius:
                      BorderRadius.circular(16),
                ),
                child: Icon(
                  Icons.refresh,
                  color: Theme.of(context)
                      .colorScheme
                      .onPrimaryContainer,
                ),
              ),

              const SizedBox(width: 18),

              Expanded(
                child: Column(
                  crossAxisAlignment:
                      CrossAxisAlignment
                          .start,
                  children: [
                    Text(
                      '$dueCount ${dueCount == 1 ? 'word' : 'words'} due',
                      style:
                          const TextStyle(
                        fontSize: 18,
                        fontWeight:
                            FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      'Ready for today\'s review',
                      style: TextStyle(
                        color: Colors.grey,
                      ),
                    ),
                  ],
                ),
              ),

              const Icon(
                Icons.chevron_right,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class DailyCompleteTile
    extends StatelessWidget {
  const DailyCompleteTile({
    super.key,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding:
            const EdgeInsets.all(20),
        child: Row(
          children: [
            Container(
              width: 55,
              height: 55,
              decoration: BoxDecoration(
                color: Theme.of(context)
                    .colorScheme
                    .secondaryContainer,
                borderRadius:
                    BorderRadius.circular(16),
              ),
              child: Icon(
                Icons.check,
                color: Theme.of(context)
                    .colorScheme
                    .onSecondaryContainer,
              ),
            ),

            const SizedBox(width: 18),

            const Expanded(
              child: Column(
                crossAxisAlignment:
                    CrossAxisAlignment
                        .start,
                children: [
                  Text(
                    'You\'re done for today!',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight:
                          FontWeight.bold,
                    ),
                  ),
                  SizedBox(height: 4),
                  Text(
                    'No reviews are due.',
                    style: TextStyle(
                      color: Colors.grey,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}