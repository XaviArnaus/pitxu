import re

class Rating:

    target: str = None
    rating: float = None

    def __init__(self, target: str, rating: float):
        self.target = target
        self.rating = rating

    def __str__(self) -> str:
        return f"'{self.target}'[{self.rating}]"

class BestMatch:

    ratings: list[Rating] = None
    bestMatch: Rating = None
    bestMatchIndex: int = None
    
    def __init__(self, ratings: list[Rating], bestMatch: Rating, bestMatchIndex: int):
        self.ratings = ratings
        self.bestMatch = bestMatch
        self.bestMatchIndex = bestMatchIndex

    def __str__(self) -> str:
        return f'{self.bestMatchIndex}:{self.bestMatch}'

class StringSimilarity:

    @staticmethod
    def compareTwoStrings(first: str, second: str) -> float:
        # if both are None
        if first is None and second is None:
            return 1
        # as both are not None, if one of them is None then return 0
        if first is None or second is None:
            return 0
        
        first = re.sub(r'\s+\b|\b\s', '', first) # remove all whitespace
        second = re.sub(r'\s+\b|\b\s', '', second) # remove all whitespace

        # if both are empty strings
        if first == '' and second == '':
            return 1
        # if only one is an empty string
        if first == '' or second == '':
            return 0
        # identical
        if first == second:
            return 1
        # both are 1-letter strings
        if len(first) == 1 and len(second) == 1:
            return 0
        # if either is a 1-letter string
        if len(first) < 2 or len(second) < 2:
            return 0

        firstBigrams = {}
        for i in range(len(first) - 1):
            bigram = first[i:i + 2]
            count = firstBigrams.get(bigram, 0) + 1
            firstBigrams[bigram] = count

        intersectionSize = 0
        for i in range(len(second) - 1):
            bigram = second[i:i + 2]
            count = firstBigrams.get(bigram, 0)

            if count > 0:
                firstBigrams[bigram] = count - 1
                intersectionSize += 1

        return (2.0 * intersectionSize) / (len(first) + len(second) - 2)


    @staticmethod
    def findBestMatch(mainString: str, targetStrings: list[str]) -> BestMatch:
        ratings: list[Rating] = []
        bestMatchIndex: int = 0

        for i in range(len(targetStrings)):
            currentTargetString = targetStrings[i]
            currentRating = StringSimilarity.compareTwoStrings(mainString, currentTargetString)
            ratings.append(Rating(target=currentTargetString, rating=currentRating))
            if currentRating > ratings[bestMatchIndex].rating:
                bestMatchIndex = i

        bestMatch = ratings[bestMatchIndex]

        return BestMatch(ratings=ratings, bestMatch=bestMatch, bestMatchIndex=bestMatchIndex)
