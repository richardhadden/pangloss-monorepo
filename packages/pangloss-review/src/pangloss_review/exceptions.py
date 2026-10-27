class PanglossReviewError(Exception):
    """Something that cannot be done in review"""


class PanglossNotReviewableError(PanglossReviewError):
    """No such document, or it is not of a class that is reviewed"""


class PanglossSelfReviewError(PanglossReviewError):
    """A user cannot check a document they created or last edited (`REVIEW_ALLOW_SELF_REVIEW` is false)"""


class PanglossCommentTargetError(PanglossReviewError):
    """The part a comment is about is not in the document"""


class PanglossNoSuchCommentError(PanglossReviewError):
    """No such comment on the document"""
